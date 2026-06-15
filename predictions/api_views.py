import os
import secrets
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from PIL import Image, UnidentifiedImageError
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts import consts as acc_consts
from . import consts, export, live, results_sync, scoring, telegram
from .models import (
    Competition,
    League,
    Match,
    MatchScore,
    Membership,
    Prediction,
    Team,
)
from .throttles import EXPORT_THROTTLES, JOIN_LEAGUE_THROTTLES, PREDICT_THROTTLES

User = get_user_model()


# --------------------------------------------------------------------------- #
# Serialization helpers (plain dicts -> JSON)
# --------------------------------------------------------------------------- #
def _team(team):
    if not team:
        return None
    return {
        "id": team.id,
        "name": team.name_fa,
        "name_en": team.name_en,
        "code": team.code,
        "flag": team.flag_emoji,
        "group": team.group,
    }


def _avatar_url(user, request):
    """Absolute URL to a user's avatar, or None. (S3 URLs are already absolute;
    build_absolute_uri leaves them untouched and prefixes local MEDIA paths.)"""
    if not user.avatar:
        return None
    return request.build_absolute_uri(user.avatar.url)


def _profile(user, request):
    """Full profile of a single user (own profile or another player's).

    Email is private: it's only returned on the requester's own profile, never
    when viewing another player (so the players directory can't be scraped for
    everyone's email address)."""
    is_self = user.id == request.user.id
    return {
        "id": user.id,
        # email and admin flag are private: only returned on one's own profile.
        "email": user.email if is_self else "",
        "is_admin": _is_admin(user) if is_self else False,
        "display_name": user.display_name,
        "public_name": user.public_name,
        "avatar": _avatar_url(user, request),
        "bio": user.bio,
        "location": user.location,
        "social_handle": user.social_handle,
        "favorite_team": _team(user.favorite_team),
        "joined_at": user.date_joined.isoformat(),
    }


def _player_card(user, request):
    """Compact player summary for the global players directory."""
    return {
        "id": user.id,
        "public_name": user.public_name,
        "avatar": _avatar_url(user, request),
        "location": user.location,
        "favorite_team": _team(user.favorite_team),
        # `league_count` is annotated by the players() query.
        "league_count": getattr(user, "league_count", 0),
    }


def _live_dict(match):
    """In-play state of a match (display only), or None when there is none.
    An official result always wins: once a match is finished, live state is
    suppressed even if the provider's last word still lingers in the DB."""
    if not match.live_status or match.is_finished:
        return None
    return {
        "status": match.live_status,
        "status_label": consts.LIVE_STATUS_LABELS.get(match.live_status),
        "minute": match.live_minute or None,
        "home": match.live_home_score,
        "away": match.live_away_score,
    }


def _match_dict(match, league, now, prediction=None, score=None):
    is_open = match.is_open_for(league.lock_minutes, now)
    return {
        "id": match.id,
        "stage": match.stage,
        "stage_label": consts.STAGE_LABELS.get(match.stage),
        "kickoff": match.kickoff.isoformat(),
        "venue": match.venue or None,
        "home_team": _team(match.home_team),
        "away_team": _team(match.away_team),
        # Persian bracket-slot placeholders, shown when the team isn't decided yet
        # (falls back to "نامشخص" when even the slot label is unknown).
        "home_label": consts.bracket_label_fa(match.home_label) if not match.home_team_id else None,
        "away_label": consts.bracket_label_fa(match.away_label) if not match.away_team_id else None,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "live": _live_dict(match),
        "is_finished": match.is_finished,
        "is_open": is_open,
        "can_predict": is_open and bool(match.home_team_id and match.away_team_id),
        "lock_time": match.lock_time(league.lock_minutes).isoformat(),
        "my_prediction": (
            {"home": prediction.predicted_home, "away": prediction.predicted_away}
            if prediction else None
        ),
        "my_points": float(score.points) if score else None,
        "tier": score.tier if score else None,
        "tier_label": consts.TIER_LABELS.get(score.tier) if score else None,
    }


def _league_dict(league, membership, request):
    return {
        "slug": league.slug,
        "name": league.name,
        "description": league.description,
        "competition": {
            "name": league.competition.name,
            "slug": league.competition.slug,
        },
        "member_count": league.memberships.count(),
        "is_owner": membership.is_owner,
        "role": membership.role,
        "invite_code": league.invite_code if membership.is_owner else None,
        # Whether other members' predictions are shown after a match locks
        # (owner-toggleable). The frontend renders the toggle for the owner.
        "reveal_predictions": league.reveal_predictions,
        # The export key/link is shared with the whole league — anyone can use it
        # to download the results spreadsheet (upcoming picks stay hidden inside it).
        "export_key": league.export_key,
        "export_url": request.build_absolute_uri(league.export_path()),
        "scoring": {
            "points_exact": league.points_exact,
            "points_correct_diff": league.points_correct_diff,
            "points_correct_winner": league.points_correct_winner,
            "points_participation": league.points_participation,
            "lock_minutes": league.lock_minutes,
            "stage_multipliers": [
                {
                    "stage": stage,
                    "label": consts.STAGE_LABELS[stage],
                    "multiplier": float(league.multiplier_for(stage)),
                }
                for stage in consts.STAGE_ORDER
            ],
        },
    }


def _league_card(membership):
    league = membership.league
    return {
        "slug": league.slug,
        "name": league.name,
        "competition": league.competition.name,
        "role": membership.role,
        "is_owner": membership.is_owner,
        "member_count": league.memberships.count(),
    }


def _get_membership(request, slug):
    league = get_object_or_404(League, slug=slug)
    try:
        return Membership.objects.select_related("league", "league__competition").get(
            league=league, user=request.user
        )
    except Membership.DoesNotExist:
        raise NotFound(consts.MSG_NOT_A_MEMBER)


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
def _clean(value, max_length):
    """Trim whitespace and cap length so we never overflow a DB column."""
    return (value or "").strip()[:max_length]


def _as_bool(value) -> bool:
    """Coerce a JSON/string flag to a real bool. JSON booleans arrive as bool
    already; guard the common string/number forms so e.g. "false" isn't truthy."""
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return bool(value)


def _update_profile(user, data):
    """Apply a partial profile update from a PATCH body. Only keys present in the
    body are touched, so the same endpoint handles single- and multi-field edits."""
    if "display_name" in data:
        user.display_name = _clean(data.get("display_name"), 60)
    if "bio" in data:
        bio = (data.get("bio") or "").strip()
        if len(bio) > acc_consts.BIO_MAX_LENGTH:
            raise ValidationError({"bio": acc_consts.ERR_BIO_TOO_LONG})
        user.bio = bio
    if "location" in data:
        user.location = _clean(data.get("location"), acc_consts.LOCATION_MAX_LENGTH)
    if "social_handle" in data:
        user.social_handle = _clean(data.get("social_handle"), acc_consts.SOCIAL_MAX_LENGTH)
    if "favorite_team_id" in data:
        team_id = data.get("favorite_team_id")
        if team_id in (None, "", 0):
            user.favorite_team = None
        else:
            try:
                user.favorite_team = Team.objects.get(id=team_id)
            except (Team.DoesNotExist, ValueError, TypeError):
                raise ValidationError(
                    {"favorite_team_id": acc_consts.ERR_FAVORITE_TEAM_INVALID}
                )
    user.save()


@api_view(["GET", "PATCH"])
def me(request):
    """The signed-in user's own profile — GET to read, PATCH to edit text fields.
    (The avatar image is uploaded separately via my_avatar.)"""
    user = request.user
    if request.method == "PATCH":
        _update_profile(user, request.data)
    return Response(_profile(user, request))


@api_view(["POST", "DELETE"])
def my_avatar(request):
    """Upload (multipart `avatar`) or remove the signed-in user's profile photo."""
    user = request.user

    if request.method == "DELETE":
        if user.avatar:
            user.avatar.delete(save=False)
            user.save(update_fields=["avatar"])
        return Response(_profile(user, request))

    upload = request.FILES.get("avatar")
    if not upload:
        raise ValidationError({"avatar": acc_consts.ERR_AVATAR_REQUIRED})
    if upload.size > acc_consts.AVATAR_MAX_BYTES:
        raise ValidationError({"avatar": acc_consts.ERR_AVATAR_TOO_LARGE})
    if upload.content_type not in acc_consts.AVATAR_CONTENT_TYPES:
        raise ValidationError({"avatar": acc_consts.ERR_AVATAR_BAD_TYPE})
    # Don't trust the declared content type — confirm it's a real, decodable image.
    try:
        Image.open(upload).verify()
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError({"avatar": acc_consts.ERR_AVATAR_BAD_TYPE})
    upload.seek(0)  # verify() consumed the stream

    ext = os.path.splitext(upload.name)[1].lower()
    if ext not in acc_consts.AVATAR_EXTENSIONS:
        ext = acc_consts.AVATAR_DEFAULT_EXTENSION
    # A random suffix both avoids collisions and busts the browser/CDN cache.
    filename = f"user_{user.id}_{secrets.token_hex(4)}{ext}"
    if user.avatar:
        user.avatar.delete(save=False)
    user.avatar.save(filename, upload, save=True)
    return Response(_profile(user, request))


def _telegram_status(user, request):
    """The signed-in user's Telegram link state for the connect UI. The deep
    link is only handed out while unlinked (and only when a bot is configured)."""
    linked = user.telegram_chat_id is not None
    return {
        "configured": telegram.is_configured(),
        "linked": linked,
        "notify": user.telegram_notify,
        "deep_link": None if linked else telegram.deep_link(user),
    }


@api_view(["GET", "PATCH"])
def me_telegram(request):
    """Read or update the signed-in user's Telegram link.

    GET also drains pending bot updates (a cheap no-op when nothing is waiting),
    so the connect page can poll this endpoint and see the link complete within
    a couple of seconds of the user tapping Start — no webhook needed.
    PATCH toggles `notify` or unlinks (`{"unlink": true}`)."""
    user = request.user
    if request.method == "PATCH":
        if _as_bool(request.data.get("unlink")):
            user.telegram_chat_id = None
            user.telegram_link_token = ""
            user.telegram_link_token_at = None
            user.save(update_fields=[
                "telegram_chat_id", "telegram_link_token", "telegram_link_token_at",
            ])
        elif "notify" in request.data:
            user.telegram_notify = _as_bool(request.data.get("notify"))
            user.save(update_fields=["telegram_notify"])
    else:
        # A just-tapped "Start" lands here via the poll; pick up the new chat id.
        telegram.poll_updates()
        user.refresh_from_db()
    return Response(_telegram_status(user, request))


@api_view(["POST"])
@authentication_classes([])      # called by the scheduler, not a signed-in user
@permission_classes([AllowAny])
def task_tick(request):
    """Periodic job trigger (GitHub Actions cron): pulls bot updates, refreshes
    live scores, finalizes due results, and sends due reminders. Gated by the
    secret TASK_TRIGGER_KEY (sent in the X-Task-Key header); disabled — 403 —
    when that key isn't configured, so it can never be triggered anonymously."""
    key = (settings.TASK_TRIGGER_KEY or "").strip()
    provided = request.headers.get(consts.TELEGRAM_TASK_KEY_HEADER, "")
    if not key or not secrets.compare_digest(provided, key):
        raise PermissionDenied(consts.MSG_TASK_FORBIDDEN)
    return Response(telegram.run_tick(timezone.now()))


@api_view(["GET"])
def teams(request):
    """Teams of the active competition(s) — used by the favorite-team picker."""
    qs = Team.objects.filter(competition__is_active=True).order_by("group", "name_fa")
    return Response([_team(t) for t in qs])


@api_view(["GET"])
def players(request):
    """Global directory of every active player."""
    users = (
        User.objects.filter(is_active=True)
        .select_related("favorite_team")
        .annotate(league_count=Count("memberships", distinct=True))
        .order_by("display_name", "email")
    )
    return Response([_player_card(u, request) for u in users])


@api_view(["GET"])
def player_detail(request, user_id):
    """A single player's public profile plus the leagues they share with me."""
    user = get_object_or_404(
        User.objects.select_related("favorite_team"), id=user_id, is_active=True
    )
    my_league_ids = Membership.objects.filter(user=request.user).values_list(
        "league_id", flat=True
    )
    shared = (
        Membership.objects.filter(user=user, league_id__in=my_league_ids)
        .select_related("league", "league__competition")
        .order_by("-joined_at")
    )
    return Response({
        "profile": _profile(user, request),
        "is_me": user.id == request.user.id,
        "stats": {
            "leagues": Membership.objects.filter(user=user).count(),
            "predictions": Prediction.objects.filter(membership__user=user).count(),
        },
        "shared_leagues": [
            {
                "slug": m.league.slug,
                "name": m.league.name,
                "competition": m.league.competition.name,
            }
            for m in shared
        ],
    })


@api_view(["GET"])
def competitions(request):
    data = [
        {"id": c.id, "name": c.name, "slug": c.slug}
        for c in Competition.objects.filter(is_active=True)
    ]
    return Response(data)


@api_view(["GET", "POST"])
def leagues(request):
    if request.method == "GET":
        memberships = (
            Membership.objects.filter(user=request.user)
            .select_related("league", "league__competition")
            .order_by("-joined_at")
        )
        return Response([_league_card(m) for m in memberships])

    # POST -> create a league
    name = (request.data.get("name") or "").strip()
    competition_id = request.data.get("competition_id")
    description = (request.data.get("description") or "").strip()
    if not name:
        raise ValidationError({"name": "نام مسابقه لازم است."})
    try:
        competition = Competition.objects.get(id=competition_id, is_active=True)
    except (Competition.DoesNotExist, ValueError, TypeError):
        raise ValidationError({"competition_id": "تورنمنت نامعتبر است."})

    league = League.objects.create(
        name=name, competition=competition, description=description,
        owner=request.user,
    )
    membership = Membership.objects.create(
        league=league, user=request.user, role=consts.Role.OWNER
    )
    return Response(_league_dict(league, membership, request), status=201)


@api_view(["POST"])
@throttle_classes(JOIN_LEAGUE_THROTTLES)
def join_league(request):
    code = (request.data.get("invite_code") or "").strip().upper()
    try:
        league = League.objects.get(invite_code=code, is_active=True)
    except League.DoesNotExist:
        raise NotFound(consts.MSG_INVALID_INVITE)

    membership, created = Membership.objects.get_or_create(
        league=league, user=request.user, defaults={"role": consts.Role.MEMBER}
    )
    return Response({"slug": league.slug, "name": league.name, "created": created})


@api_view(["GET", "PATCH"])
def league_detail(request, slug):
    membership = _get_membership(request, slug)
    league = membership.league
    if request.method == "PATCH":
        # Only the league owner (its "admin") may change settings.
        if not membership.is_owner:
            raise PermissionDenied(consts.MSG_OWNER_ONLY)
        if "reveal_predictions" in request.data:
            league.reveal_predictions = _as_bool(request.data.get("reveal_predictions"))
            league.save(update_fields=["reveal_predictions"])
    return Response(_league_dict(league, membership, request))


@api_view(["GET"])
def league_matches(request, slug):
    membership = _get_membership(request, slug)
    league = membership.league
    now = timezone.now()

    predictions = {p.match_id: p for p in Prediction.objects.filter(membership=membership)}
    scores = {s.match_id: s for s in membership.scores.all()}
    matches = (
        Match.objects.filter(competition=league.competition)
        .select_related("home_team", "away_team")
        .order_by("kickoff", "match_number")
    )
    data = [
        _match_dict(m, league, now, predictions.get(m.id), scores.get(m.id))
        for m in matches
    ]
    return Response(data)


@api_view(["POST"])
@throttle_classes(PREDICT_THROTTLES)
def submit_predictions(request, slug):
    membership = _get_membership(request, slug)
    league = membership.league
    now = timezone.now()

    items = request.data.get("predictions", [])
    if not isinstance(items, list):
        raise ValidationError({"predictions": "قالب نامعتبر است."})

    match_ids = [i.get("match_id") for i in items if isinstance(i, dict)]
    matches = {
        m.id: m for m in Match.objects.filter(
            id__in=match_ids, competition=league.competition
        )
    }

    saved = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        match = matches.get(item.get("match_id"))
        if not match or not match.is_open_for(league.lock_minutes, now):
            continue
        if not (match.home_team_id and match.away_team_id):
            continue
        try:
            home, away = int(item["home"]), int(item["away"])
        except (KeyError, ValueError, TypeError):
            continue
        if home < 0 or away < 0:
            continue
        Prediction.objects.update_or_create(
            membership=membership, match=match,
            defaults={"predicted_home": home, "predicted_away": away},
        )
        saved += 1

    return Response({"saved": saved})


@api_view(["GET"])
def league_leaderboard(request, slug):
    membership = _get_membership(request, slug)
    rows, is_live = scoring.live_leaderboard(membership.league)
    return Response({
        # True while at least one match carries in-play state: the live_*
        # fields then differ from the official ones and deserve their own tab.
        "is_live": is_live,
        "rows": [
            {
                "rank": row["rank"],
                "name": row["name"],
                "total": float(row["total"]),
                "played": row["played"],
                "exact_count": row["exact_count"],
                "is_me": row["membership"].user_id == request.user.id,
                "live_rank": row["live_rank"],
                "live_total": float(row["live_total"]),
                "live_points": float(row["live_points"]),
            }
            for row in rows
        ],
    })


@api_view(["GET"])
def live_scores(request):
    """Current in-play scores across the active competitions.

    Lazily refreshes from the live provider when the stored snapshot is stale
    (at most one upstream request per consts.LIVE_REFRESH_SECONDS, none at all
    when no match can be live) and returns every match that currently carries
    live state. Officially finished matches never appear — the real result has
    taken over by then."""
    now = timezone.now()
    competitions = list(Competition.objects.filter(is_active=True))
    for competition in competitions:
        live.refresh_if_stale(competition, now)
        # When a match looks over, pull the official result so it finalizes
        # (and everyone's points recompute) minutes after full time — no cron.
        results_sync.finalize_if_due(competition, now)

    matches = (
        Match.objects.filter(competition__in=competitions)
        .exclude(live_status=consts.LiveStatus.NONE)
        .exclude(status=consts.MatchStatus.FINISHED)
        .select_related("home_team", "away_team")
        .order_by("kickoff", "match_number")
    )
    return Response({
        "checked_at": now.isoformat(),
        "matches": [
            {
                "id": m.id,
                "kickoff": m.kickoff.isoformat(),
                "home_team": _team(m.home_team),
                "away_team": _team(m.away_team),
                **(_live_dict(m) or {}),
            }
            for m in matches
        ],
    })


@api_view(["GET"])
@authentication_classes([])      # public, key-gated: no Clerk token required
@permission_classes([AllowAny])
@throttle_classes(EXPORT_THROTTLES)
def export_league(request, key):
    """Download a league's results as an .xlsx file, gated only by its export key.

    Deliberately public so the key can be shared with anyone (group chats, etc.).
    It exposes no more than members already see in-app, and the builder blanks out
    predictions for matches that haven't locked yet, so upcoming picks never leak."""
    league = get_object_or_404(League, export_key=key)
    content = export.league_xlsx_bytes(league)

    response = HttpResponse(content, content_type=consts.EXPORT_CONTENT_TYPE)
    filename = consts.EXPORT_FILENAME_TEMPLATE.format(slug=league.slug)
    # Slugs are normally ASCII now, so the plain `filename` can carry the real name;
    # the RFC 5987 `filename*` still preserves any non-ASCII name, and we keep a
    # generic ASCII fallback for the rare slug that isn't ASCII-safe.
    ascii_name = filename if filename.isascii() else consts.EXPORT_FILENAME_FALLBACK
    response["Content-Disposition"] = consts.EXPORT_CONTENT_DISPOSITION.format(
        ascii=ascii_name, encoded=quote(filename),
    )
    return response


@api_view(["GET"])
def league_members(request, slug):
    """Members of a league with their profile summary + standing in this league."""
    membership = _get_membership(request, slug)
    league = membership.league

    rows = scoring.leaderboard(league)  # ranked rows carry the Membership objects
    users = {
        u.id: u
        for u in User.objects.filter(
            id__in=[r["membership"].user_id for r in rows]
        ).select_related("favorite_team")
    }
    data = []
    for row in rows:
        m = row["membership"]
        user = users[m.user_id]
        data.append({
            "rank": row["rank"],
            "id": user.id,
            "name": user.public_name,
            "avatar": _avatar_url(user, request),
            "favorite_team": _team(user.favorite_team),
            "role": m.role,
            "role_label": consts.ROLE_LABELS.get(m.role),
            "joined_at": m.joined_at.isoformat(),
            "total": float(row["total"]),
            "played": row["played"],
            "exact_count": row["exact_count"],
            "is_me": m.user_id == request.user.id,
        })
    return Response(data)


@api_view(["GET"])
def match_detail(request, slug, match_id):
    membership = _get_membership(request, slug)
    league = membership.league
    match = get_object_or_404(Match, id=match_id, competition=league.competition)
    now = timezone.now()

    # A match's picks are revealed once it locks (default: 30m before kickoff) —
    # but only if the league owner left reveal turned on. Before lock (or when the
    # owner disabled reveal) we still list *who* has predicted — names only,
    # scores hidden — so members see participation without copying a prediction.
    revealed = league.reveal_predictions and not match.is_open_for(league.lock_minutes, now)
    scores = {s.membership_id: s for s in match.scores.all()} if revealed else {}
    qs = (
        Prediction.objects.filter(match=match, membership__league=league)
        .select_related("membership", "membership__user")
    )

    my_pred = None
    others = []
    for p in qs:
        if p.membership_id == membership.id:
            my_pred = p
        s = scores.get(p.membership_id) if revealed else None
        others.append({
            "name": p.membership.user.public_name,
            "is_me": p.membership_id == membership.id,
            # Scores stay hidden until the match locks.
            "home": p.predicted_home if revealed else None,
            "away": p.predicted_away if revealed else None,
            "points": float(s.points) if s else None,
            "tier_label": consts.TIER_LABELS.get(s.tier) if s else None,
        })

    return Response({
        "match": _match_dict(match, league, now, my_pred),
        "revealed": revealed,
        # Surfaced so the UI can explain *why* picks are hidden: not locked yet
        # vs. the owner turned reveal off for this league.
        "reveal_predictions": league.reveal_predictions,
        "lock_time": match.lock_time(league.lock_minutes).isoformat(),
        "member_count": league.memberships.count(),
        "predictions": others,
    })


@api_view(["GET"])
def league_all_predictions(request, slug):
    """Every member's prediction for every match in one payload — the in-app
    "who predicted what" board. Same reveal rules as match_detail: a match's
    picks stay hidden until it locks (and only if the owner left reveal on);
    before that we list *who* predicted (participation) but not their score."""
    membership = _get_membership(request, slug)
    league = membership.league
    now = timezone.now()

    memberships = list(Membership.objects.filter(league=league).select_related("user"))
    users = {
        u.id: u
        for u in User.objects.filter(id__in=[m.user_id for m in memberships])
    }
    # predictions[match_id][membership_id] and scores[match_id][membership_id]
    preds = {}
    for p in Prediction.objects.filter(membership__league=league):
        preds.setdefault(p.match_id, {})[p.membership_id] = p
    scores = {}
    for s in MatchScore.objects.filter(membership__league=league):
        scores.setdefault(s.match_id, {})[s.membership_id] = s

    matches = (
        Match.objects.filter(competition=league.competition)
        .select_related("home_team", "away_team")
        .order_by("kickoff", "match_number")
    )

    out = []
    for match in matches:
        is_open = match.is_open_for(league.lock_minutes, now)
        revealed = league.reveal_predictions and not is_open
        match_preds = preds.get(match.id, {})
        match_scores = scores.get(match.id, {}) if revealed else {}
        rows = []
        for m in memberships:
            p = match_preds.get(m.id)
            if not p:
                continue  # only members who actually predicted
            s = match_scores.get(m.id)
            rows.append({
                "name": users[m.user_id].public_name,
                "avatar": _avatar_url(users[m.user_id], request),
                "is_me": m.user_id == request.user.id,
                "home": p.predicted_home if revealed else None,
                "away": p.predicted_away if revealed else None,
                "points": float(s.points) if s else None,
                "tier": s.tier if s else None,
                "tier_label": consts.TIER_LABELS.get(s.tier) if s else None,
            })
        # Me first, then highest scorers, then by name — stable and friendly.
        rows.sort(key=lambda r: (not r["is_me"], -(r["points"] or 0), r["name"]))
        out.append({
            "id": match.id,
            "stage": match.stage,
            "stage_label": consts.STAGE_LABELS.get(match.stage),
            "kickoff": match.kickoff.isoformat(),
            "home_team": _team(match.home_team),
            "away_team": _team(match.away_team),
            "home_label": consts.bracket_label_fa(match.home_label) if not match.home_team_id else None,
            "away_label": consts.bracket_label_fa(match.away_label) if not match.away_team_id else None,
            "home_score": match.home_score,
            "away_score": match.away_score,
            "is_finished": match.is_finished,
            # is_open lets the UI tell a still-open match apart from one that is
            # locked/finished but kept private by the owner (both have revealed=False).
            "is_open": is_open,
            "revealed": revealed,
            "predicted_count": len(rows),
            "predictions": rows,
        })

    return Response({
        "reveal_predictions": league.reveal_predictions,
        "lock_minutes": league.lock_minutes,
        "member_count": len(memberships),
        "matches": out,
    })


# --------------------------------------------------------------------------- #
# In-app admin: manual result entry (gated to admins; entering a score updates
# the scoreboard automatically via the Match post_save signal).
# --------------------------------------------------------------------------- #
def _is_admin(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    email = (user.email or "").lower()
    return bool(email) and email in settings.ADMIN_EMAILS


def _admin_match_dict(match):
    return {
        "id": match.id,
        "match_number": match.match_number,
        "stage": match.stage,
        "stage_label": consts.STAGE_LABELS.get(match.stage),
        "kickoff": match.kickoff.isoformat(),
        "venue": match.venue or None,
        "competition": {"name": match.competition.name, "slug": match.competition.slug},
        "home_team": _team(match.home_team),
        "away_team": _team(match.away_team),
        "home_label": consts.bracket_label_fa(match.home_label) if not match.home_team_id else None,
        "away_label": consts.bracket_label_fa(match.away_label) if not match.away_team_id else None,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "is_finished": match.is_finished,
        "status": match.status,
    }


@api_view(["GET"])
def admin_matches(request):
    if not _is_admin(request.user):
        raise PermissionDenied(consts.MSG_ADMIN_ONLY)
    qs = (
        Match.objects.select_related("home_team", "away_team", "competition")
        .order_by("kickoff", "match_number")
    )
    comp = request.query_params.get("competition")
    qs = qs.filter(competition__slug=comp) if comp else qs.filter(competition__is_active=True)
    return Response([_admin_match_dict(m) for m in qs])


@api_view(["POST"])
def admin_set_result(request, match_id):
    if not _is_admin(request.user):
        raise PermissionDenied(consts.MSG_ADMIN_ONLY)
    match = get_object_or_404(Match, id=match_id)

    home, away = request.data.get("home_score"), request.data.get("away_score")
    # Both empty/None -> clear the result (reverts the match to scheduled).
    if home in (None, "") and away in (None, ""):
        match.home_score = match.away_score = None
        match.save()
        return Response(_admin_match_dict(match))

    try:
        home_i, away_i = int(home), int(away)
    except (TypeError, ValueError):
        raise ValidationError({"detail": consts.MSG_INVALID_RESULT})
    if home_i < 0 or away_i < 0:
        raise ValidationError({"detail": consts.MSG_INVALID_RESULT})

    match.home_score, match.away_score = home_i, away_i
    match.save()  # status -> FINISHED; post_save signal recomputes everyone's points
    return Response(_admin_match_dict(match))
