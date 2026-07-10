import os
import secrets
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
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
from . import consts, export, fun_stats, live, recap, results_sync, scoring, telegram
from .models import (
    BonusPrediction,
    BonusScore,
    Competition,
    League,
    Match,
    MatchScore,
    Membership,
    PlayerCandidate,
    Prediction,
    Team,
    TournamentOutcome,
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
        # For a knockout match settled on penalties, the side that advanced
        # (HOME/AWAY); null otherwise. home_score/away_score stay the 120' draw.
        "penalty_winner": match.penalty_winner or None,
        "live": _live_dict(match),
        "is_finished": match.is_finished,
        # When False, this match is voided: it earns no points and is left out of
        # the standings, though predictions and the result are still shown.
        "counts_for_scoring": match.count_for_scoring,
        "is_open": is_open,
        "can_predict": is_open and bool(match.home_team_id and match.away_team_id),
        "lock_time": match.lock_time(league.lock_minutes).isoformat(),
        "my_prediction": (
            {
                "home": prediction.predicted_home,
                "away": prediction.predicted_away,
                # Who the member picked to advance on penalties (HOME/AWAY), set
                # only on a knockout draw prediction; null otherwise.
                "advancer": prediction.predicted_advancer or None,
            }
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
        # Owner's one-time decision on the 2× knockout boost (PENDING/ACCEPTED/
        # DECLINED). The frontend shows the opt-in prompt while it's PENDING.
        "boost_decision": league.boost_decision,
        # The current QF-onward multiplier the owner can tune (default 1.5, or 2×
        # once boosted). Editable from the league page; see BoostPrompt.
        "boost_multiplier": float(league.boost_multiplier),
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
            # Tournament-wide bonus questions (enabled per league via bonus_lock_at).
            "bonus_enabled": league.bonus_enabled,
            "bonus_lock_at": league.bonus_lock_at.isoformat() if league.bonus_lock_at else None,
            "points_champion": league.points_champion,
            "points_runner_up": league.points_runner_up,
            "points_third": league.points_third,
            "points_fourth": league.points_fourth,
            "points_golden_boot": league.points_golden_boot,
            "points_golden_ball": league.points_golden_ball,
            "points_league_winner": league.points_league_winner,
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


# -- matchday recap serialization (rich objects from recap.py -> JSON) -------- #
def _recap_player(membership, request):
    user = membership.user
    return {
        "id": user.id,
        "name": user.public_name,
        "avatar": _avatar_url(user, request),
        "is_me": user.id == request.user.id,
    }


def _recap_match_mini(match):
    """A compact match card for the recap (no per-viewer prediction fields)."""
    return {
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
    }


def _recap_call(score, match, prediction):
    """One member's standout prediction: the fixture, their pick, and the payoff."""
    return {
        "match": _recap_match_mini(match),
        "prediction": {"home": prediction.predicted_home, "away": prediction.predicted_away},
        "points": float(score.points),
        "tier": score.tier,
        "tier_label": consts.TIER_LABELS.get(score.tier),
    }


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


def _parse_boost_multiplier(value) -> Decimal:
    """Validate a custom QF-onward multiplier from the request body: a number in
    [BOOST_MIN_MULTIPLIER, BOOST_MAX_MULTIPLIER], quantized to 2 places. Raises
    ValidationError otherwise."""
    try:
        parsed = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        parsed = None
    if parsed is None or not (
        consts.BOOST_MIN_MULTIPLIER <= parsed <= consts.BOOST_MAX_MULTIPLIER
    ):
        raise ValidationError(consts.MSG_BOOST_MULTIPLIER_INVALID.format(
            min=consts.BOOST_MIN_MULTIPLIER, max=consts.BOOST_MAX_MULTIPLIER,
        ))
    return parsed


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
        "notify_matches": user.telegram_notify_matches,
        "deep_link": None if linked else telegram.deep_link(user),
    }


@api_view(["GET", "PATCH"])
def me_telegram(request):
    """Read or update the signed-in user's Telegram link.

    GET also drains pending bot updates (a cheap no-op when nothing is waiting),
    so the connect page can poll this endpoint and see the link complete within
    a couple of seconds of the user tapping Start — no webhook needed.
    PATCH toggles `notify` (reminders) or `notify_matches` (live match-event
    DMs), or unlinks (`{"unlink": true}`)."""
    user = request.user
    if request.method == "PATCH":
        if _as_bool(request.data.get("unlink")):
            user.telegram_chat_id = None
            user.telegram_link_token = ""
            user.telegram_link_token_at = None
            user.save(update_fields=[
                "telegram_chat_id", "telegram_link_token", "telegram_link_token_at",
            ])
        else:
            # Both toggles are independent — apply every one the request carries
            # (a single PATCH may set notify and notify_matches together).
            changed = []
            if "notify" in request.data:
                user.telegram_notify = _as_bool(request.data.get("notify"))
                changed.append("telegram_notify")
            if "notify_matches" in request.data:
                user.telegram_notify_matches = _as_bool(request.data.get("notify_matches"))
                changed.append("telegram_notify_matches")
            if changed:
                user.save(update_fields=changed)
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
        if "boost_decision" in request.data:
            action = request.data.get("boost_decision")
            if action == consts.BOOST_ACTION_ACCEPT:
                league.apply_boost()
                # QF+ isn't scored yet, so this only affects future matches; the
                # recompute keeps already-finished stages consistent regardless.
                scoring.recompute_league_scores(league)
            elif action == consts.BOOST_ACTION_DECLINE:
                league.decline_boost()
            else:
                raise ValidationError(consts.MSG_BOOST_ACTION_INVALID)
        if "boost_multiplier" in request.data:
            value = _parse_boost_multiplier(request.data.get("boost_multiplier"))
            league.set_boost_multiplier(value)
            scoring.recompute_league_scores(league)

        # Owner turns the tournament-wide bonus predictions on/off: a datetime
        # enables the feature and sets the pick deadline; null/"" turns it off.
        if "bonus_lock_at" in request.data:
            raw = request.data.get("bonus_lock_at")
            if raw in (None, ""):
                league.bonus_lock_at = None
            else:
                dt = parse_datetime(raw) if isinstance(raw, str) else None
                if dt is None:
                    raise ValidationError({"bonus_lock_at": consts.MSG_BONUS_BAD_DATETIME})
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt)
                league.bonus_lock_at = dt
            league.save(update_fields=["bonus_lock_at"])
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
        # An advancer pick only counts on a knockout *draw* prediction; for any
        # other pick it's cleared, so flipping a draw to a winner (or back) never
        # leaves a stale advancer behind. Whatever the client sends is normalized
        # to HOME/AWAY/"" here, so an out-of-band submit can't store garbage.
        advancer = (item.get("advancer") or "").strip().upper()
        if not (match.stage in consts.KNOCKOUT_STAGES and home == away
                and advancer in consts.ADVANCER_VALUES):
            advancer = consts.Advancer.NONE
        Prediction.objects.update_or_create(
            membership=membership, match=match,
            defaults={
                "predicted_home": home, "predicted_away": away,
                "predicted_advancer": advancer,
            },
        )
        saved += 1

    return Response({"saved": saved})


@api_view(["GET"])
def league_leaderboard(request, slug):
    membership = _get_membership(request, slug)
    rows, is_live, live_matches = scoring.live_leaderboard(membership.league)
    return Response({
        # True while at least one match carries in-play state: the live_*
        # fields then differ from the official ones and deserve their own tab.
        "is_live": is_live,
        "live_matches": [
            {
                "id": m.id,
                "home_team": _team(m.home_team),
                "away_team": _team(m.away_team),
                "live_home": m.live_home_score,
                "live_away": m.live_away_score,
            }
            for m in live_matches
        ],
        "rows": [
            {
                "rank": row["rank"],
                "name": row["name"],
                "total": float(row["total"]),
                # Split of the total: per-match points vs. settled bonus points
                # (bonus_total is 0 until the tournament bonus is settled).
                "match_total": float(row["match_total"]),
                "bonus_total": float(row["bonus_total"]),
                "played": row["played"],
                "exact_count": row["exact_count"],
                "is_me": row["membership"].user_id == request.user.id,
                "live_rank": row["live_rank"],
                "live_total": float(row["live_total"]),
                "live_points": float(row["live_points"]),
                "live_picks": row["live_picks"],
                # Points-per-game view (members who predicted ≥50% of finished games).
                "avg_points": float(row["avg_points"]),
                "avg_rank": row["avg_rank"],
                "eligible_for_avg": row["eligible_for_avg"],
            }
            for row in rows
        ],
    })


# --------------------------------------------------------------------------- #
# Tournament-wide bonus predictions
# --------------------------------------------------------------------------- #
def _player_candidate(pc):
    return {"id": pc.id, "name": pc.name, "team": _team(pc.team)}


def _bonus_pick_value(pred, kind):
    """The selected option id for a member's pick (team / player / membership id),
    or None when nothing is picked."""
    if pred is None:
        return None
    answer_type = consts.BONUS_ANSWER_TYPE[kind]
    if answer_type == consts.BonusAnswerType.TEAM:
        return pred.team_id
    if answer_type == consts.BonusAnswerType.PLAYER:
        return pred.player_id
    return pred.target_membership_id


def _resolve_bonus_value(answer_type, value, competition, league):
    """Turn a submitted option id into the referenced object, scoped to the
    league's competition (teams/players) or the league itself (members). Returns
    None for an invalid/foreign id, so the caller can skip it."""
    try:
        vid = int(value)
    except (TypeError, ValueError):
        return None
    if answer_type == consts.BonusAnswerType.TEAM:
        return Team.objects.filter(id=vid, competition=competition).first()
    if answer_type == consts.BonusAnswerType.PLAYER:
        return PlayerCandidate.objects.filter(id=vid, competition=competition).first()
    if answer_type == consts.BonusAnswerType.MEMBER:
        return Membership.objects.filter(id=vid, league=league).first()
    return None


def _bonus_payload(request, membership, league, now):
    competition = league.competition
    preds = {p.kind: p for p in BonusPrediction.objects.filter(membership=membership)}
    outcome = TournamentOutcome.objects.filter(competition=competition).first()
    settled = outcome is not None and outcome.settled_at is not None
    my_scores = (
        {s.kind: s for s in BonusScore.objects.filter(membership=membership)}
        if settled else {}
    )
    # The frozen-standings winner is only meaningful once settled (it's the
    # answer the "who wins our league" pick was scored against).
    frozen_champ_id = scoring._frozen_league_champion_id(league) if settled else None

    members = [
        {"id": m.id, "name": m.user.public_name, "is_me": m.user_id == request.user.id}
        for m in Membership.objects.filter(league=league).select_related("user")
    ]

    questions = []
    for kind in consts.BONUS_KIND_ORDER:
        answer_type = consts.BONUS_ANSWER_TYPE[kind]
        correct_id = None
        if settled:
            if kind == consts.BonusKind.LEAGUE_WINNER:
                correct_id = frozen_champ_id
            else:
                answer = outcome.answer_for(kind)
                correct_id = answer.id if answer else None
        score = my_scores.get(kind)
        questions.append({
            "kind": kind,
            "label": consts.BONUS_KIND_LABELS[kind],
            "description": consts.BONUS_KIND_DESCRIPTIONS[kind],
            "answer_type": answer_type,
            "points": league.bonus_points_for(kind),
            "my_pick": _bonus_pick_value(preds.get(kind), kind),
            "correct": correct_id,
            "my_correct": score.correct if score else None,
            "my_points": float(score.points) if score else None,
        })

    return {
        "enabled": league.bonus_enabled,
        "is_open": league.bonus_is_open(now),
        "lock_at": league.bonus_lock_at.isoformat() if league.bonus_lock_at else None,
        "settled": settled,
        # Option lists for the three answer types.
        "teams": [
            _team(t) for t in competition.teams.select_related().order_by("group", "name_fa")
        ],
        "players": [
            _player_candidate(pc)
            for pc in competition.player_candidates.select_related("team").all()
        ],
        "members": members,
        "questions": questions,
    }


def _submit_bonus(request, membership, league, now):
    if not league.bonus_enabled:
        raise ValidationError({"detail": consts.MSG_BONUS_NOT_ENABLED})
    if not league.bonus_is_open(now):
        raise ValidationError({"detail": consts.MSG_BONUS_LOCKED})

    items = request.data.get("picks", [])
    if not isinstance(items, list):
        raise ValidationError({"picks": consts.MSG_BONUS_BAD_FORMAT})

    competition = league.competition
    saved = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if kind not in consts.BONUS_POINTS_FIELD:
            continue
        value = item.get("value")
        # Empty value clears the pick.
        if value in (None, "", 0):
            BonusPrediction.objects.filter(membership=membership, kind=kind).delete()
            saved += 1
            continue
        answer_type = consts.BONUS_ANSWER_TYPE[kind]
        obj = _resolve_bonus_value(answer_type, value, competition, league)
        if obj is None:
            continue
        # Set only the FK for this kind; clear the others so switching a pick
        # never leaves a stale reference behind.
        defaults = {"team": None, "player": None, "target_membership": None}
        if answer_type == consts.BonusAnswerType.TEAM:
            defaults["team"] = obj
        elif answer_type == consts.BonusAnswerType.PLAYER:
            defaults["player"] = obj
        else:
            defaults["target_membership"] = obj
        BonusPrediction.objects.update_or_create(
            membership=membership, kind=kind, defaults=defaults,
        )
        saved += 1

    return Response({"saved": saved})


@api_view(["GET", "POST"])
@throttle_classes(PREDICT_THROTTLES)
def league_bonus(request, slug):
    """Read the tournament-wide bonus questions (with the member's picks and,
    once settled, the correct answers + points earned), or POST picks to save.

    POST body: {"picks": [{"kind": "champion", "value": <option id>}, ...]},
    where `value` is a team / player-candidate / membership id per the question's
    answer type. Picks are only accepted while the league's bonus window is open."""
    membership = _get_membership(request, slug)
    league = membership.league
    now = timezone.now()
    if request.method == "POST":
        return _submit_bonus(request, membership, league, now)
    return Response(_bonus_payload(request, membership, league, now))


def _bonus_answer_label(pred):
    """The chosen option rendered for the reveal: {answer, flag}, or None."""
    answer_type = consts.BONUS_ANSWER_TYPE.get(pred.kind)
    if answer_type == consts.BonusAnswerType.TEAM and pred.team:
        return {"answer": pred.team.name_fa, "flag": pred.team.flag_emoji}
    if answer_type == consts.BonusAnswerType.PLAYER and pred.player:
        return {"answer": pred.player.name, "flag": ""}
    if answer_type == consts.BonusAnswerType.MEMBER and pred.target_membership:
        return {"answer": pred.target_membership.user.public_name, "flag": ""}
    return None


@api_view(["GET"])
def league_bonus_all(request, slug):
    """Everyone's bonus picks, revealed after the deadline — EXCEPT the
    "who wins our league" pick, which stays hidden until settlement (the final
    reveal), so knowing who backed whom doesn't spoil the ending."""
    membership = _get_membership(request, slug)
    league = membership.league
    now = timezone.now()
    is_open = league.bonus_is_open(now)
    revealed = league.bonus_enabled and not is_open
    outcome = TournamentOutcome.objects.filter(competition=league.competition).first()
    settled = outcome is not None and outcome.settled_at is not None

    by_kind = {}
    for p in (
        BonusPrediction.objects.filter(membership__league=league)
        .select_related("membership__user", "team", "player", "target_membership__user")
    ):
        by_kind.setdefault(p.kind, []).append(p)

    questions = []
    for kind in consts.BONUS_KIND_ORDER:
        is_league_winner = kind == consts.BonusKind.LEAGUE_WINNER
        # Outright picks reveal once the deadline passes; the league-winner pick
        # only at settlement.
        show = settled if is_league_winner else revealed
        picks = []
        if show:
            for p in by_kind.get(kind, []):
                label = _bonus_answer_label(p)
                if label is None:
                    continue
                picks.append({
                    "name": p.membership.user.public_name,
                    "is_me": p.membership_id == membership.id,
                    "answer": label["answer"],
                    "flag": label["flag"],
                })
            picks.sort(key=lambda r: (not r["is_me"], r["name"]))
        questions.append({
            "kind": kind,
            "label": consts.BONUS_KIND_LABELS[kind],
            "answer_type": consts.BONUS_ANSWER_TYPE[kind],
            "points": league.bonus_points_for(kind),
            "hidden": is_league_winner and not settled,
            "picks": picks,
        })

    return Response({
        "enabled": league.bonus_enabled,
        "is_open": is_open,
        "revealed": revealed,
        "settled": settled,
        "member_count": league.memberships.count(),
        "questions": questions,
    })


@api_view(["GET"])
def league_fun_stats(request, slug):
    membership = _get_membership(request, slug)
    data = fun_stats.build_fun_stats(membership.league, request.user.id)
    return Response(data)


@api_view(["GET"])
def league_recap(request, slug):
    """The animated end-of-day "story" for one matchday in a league.

    `?date=YYYY-MM-DD` picks the matchday (defaults to the latest finished day).
    Returns the day's results, the viewer's personal summary, and the league-wide
    superlatives — all computed in recap.py; here we just shape it into JSON."""
    membership = _get_membership(request, slug)
    data = recap.build_recap(membership.league, membership, request.query_params.get("date"))

    me = data["me"]
    if me is not None:
        best = me["best"]
        me = {
            "participated": me["participated"],
            "predicted": me["predicted"],
            "total": me["total"],
            "points": float(me["points"]),
            "hits": {
                "exact": me["hits"][consts.Tier.EXACT],
                "diff": me["hits"][consts.Tier.DIFF],
                "winner": me["hits"][consts.Tier.WINNER],
                "participation": me["hits"][consts.Tier.PARTICIPATION],
                "missed": me["hits"][consts.Tier.NONE],
            },
            "best_call": _recap_call(*best) if best else None,
            "rank_before": me["rank_before"],
            "rank_after": me["rank_after"],
            "rank_delta": me["rank_delta"],
            "total_before": float(me["total_before"]),
            "total_after": float(me["total_after"]),
            "is_top_scorer": me["is_top_scorer"],
            "day_avg": round(float(me["day_avg"]), 1),
        }

    def _move(rec):  # mover / faller share a shape: player + rank change
        return (
            {**_recap_player(rec["membership"], request),
             "from_rank": rec["from_rank"], "to_rank": rec["to_rank"],
             "delta": rec["delta"]}
            if rec else None
        )

    general = data["general"]
    if general is not None:
        ts, bc, sp = general["top_scorer"], general["best_call"], general["surprise"]
        general = {
            "top_scorer": (
                {**_recap_player(ts["membership"], request),
                 "points": float(ts["points"]), "ties": ts["ties"]}
                if ts else None
            ),
            "best_call": (
                {**_recap_player(bc["membership"], request),
                 **_recap_call(bc["score"], bc["match"], bc["prediction"]),
                 "also_count": bc["also_count"]}
                if bc else None
            ),
            "surprise": (
                {"match": _recap_match_mini(sp["match"]),
                 "correct_count": sp["correct_count"],
                 "predicted_count": sp["predicted_count"]}
                if sp else None
            ),
            "mover": _move(general["mover"]),
            "faller": _move(general["faller"]),
            "podium": [
                {**_recap_player(p["membership"], request),
                 "rank": p["rank"], "total": float(p["total"])}
                for p in general["podium"]
            ],
        }

    return Response({
        "date": data["date"],
        "available_dates": data["available_dates"],
        "matches": [
            {**_recap_match_mini(item["match"]), "predicted_count": item["predicted_count"]}
            for item in data["matches"]
        ],
        "me": me,
        "general": general,
        "scoreboard": [
            {**_recap_player(r["membership"], request),
             "rank_before": r["rank_before"], "rank_after": r["rank_after"],
             "total": float(r["total"]), "total_before": float(r["total_before"]),
             "day_points": float(r["day_points"]),
             "match_points": [float(p) for p in r["match_points"]]}
            for r in data["scoreboard"]
        ],
    })


@api_view(["GET"])
def league_progression(request, slug):
    """How every member's points and rank moved match by match.

    Returns the finished matches in chronological order (`steps`) and, per
    member, their cumulative total and rank *after* each of those matches
    (`totals`/`ranks`, aligned with `steps`) plus the points earned on each one
    (`match_points`). The frontend draws a line per player and lets the viewer
    toggle which players (and points-vs-rank) are shown."""
    membership = _get_membership(request, slug)
    steps, players = scoring.progression(membership.league)
    return Response({
        "steps": [
            {**_recap_match_mini(m), "match_number": m.match_number}
            for m in steps
        ],
        "players": [
            {
                "id": p["membership"].user_id,
                "name": p["membership"].user.public_name,
                "is_me": p["membership"].user_id == request.user.id,
                "totals": [float(t) for t in p["totals"]],
                "ranks": p["ranks"],
                "match_points": [float(x) for x in p["match_points"]],
                # Cumulative predictions-made per step — the average view divides
                # totals by this (games predicted, not finished-but-skipped).
                "played": p["played"],
                # Final standing (last step), surfaced so the UI can sort the
                # player list and seed the default selection without re-deriving it.
                "total": float(p["totals"][-1]) if p["totals"] else 0.0,
                "rank": p["ranks"][-1] if p["ranks"] else None,
            }
            for p in players
        ],
    })


@api_view(["GET"])
def player_average(request, user_id):
    """A player's average points-per-prediction over time, pooled across every
    league they're in — the profile-page chart. Same visibility as the public
    profile (player_detail): it exposes only an aggregate curve, no per-league
    breakdown or individual picks."""
    user = get_object_or_404(User, id=user_id, is_active=True)
    steps, series = scoring.user_average_series(user)
    return Response({
        "steps": [
            {**_recap_match_mini(m), "match_number": m.match_number}
            for m in steps
        ],
        "series": {
            "totals": [float(t) for t in series["totals"]],
            "played": series["played"],
            "averages": [round(float(a), 2) for a in series["averages"]],
        },
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
    changed = False
    for competition in competitions:
        if live.refresh_if_stale(competition, now):
            changed = True
        # When a match looks over, pull the official result so it finalizes
        # (and everyone's points recompute) minutes after full time — no cron.
        if results_sync.finalize_if_due(competition, now):
            changed = True
    # Drive the live match-event DMs from here too: this endpoint is polled by
    # every open client (~45s), so a goal / half-time / full-time reaches
    # Telegram within a refresh window whenever anyone has the app open — not
    # only when the external scheduler happens to fire. Gated on a real
    # refresh/finalize (each already claim-limited to one upstream hit per
    # window) so the send-heavy work runs at most once per window, however many
    # clients are polling.
    if changed:
        telegram.run_match_events(now)

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
            "advancer": (p.predicted_advancer or None) if revealed else None,
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
                "advancer": (p.predicted_advancer or None) if revealed else None,
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
            "penalty_winner": match.penalty_winner or None,
            "is_finished": match.is_finished,
            # When False, this match is voided from scoring (no points), though
            # predictions and the result are still shown.
            "counts_for_scoring": match.count_for_scoring,
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
        # Who advanced on penalties (HOME/AWAY) when a knockout was level at 120'.
        "penalty_winner": match.penalty_winner or None,
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
        match.penalty_winner = consts.Advancer.NONE
        match.save()
        return Response(_admin_match_dict(match))

    try:
        home_i, away_i = int(home), int(away)
    except (TypeError, ValueError):
        raise ValidationError({"detail": consts.MSG_INVALID_RESULT})
    if home_i < 0 or away_i < 0:
        raise ValidationError({"detail": consts.MSG_INVALID_RESULT})

    match.home_score, match.away_score = home_i, away_i
    # A knockout level at 120' is decided on penalties: record who advanced.
    # Only meaningful for a knockout draw; cleared otherwise so a decisive result
    # never carries a stale winner.
    pen = (request.data.get("penalty_winner") or "").strip().upper()
    if (match.stage in consts.KNOCKOUT_STAGES and home_i == away_i
            and pen in consts.ADVANCER_VALUES):
        match.penalty_winner = pen
    else:
        match.penalty_winner = consts.Advancer.NONE
    match.save()  # status -> FINISHED; post_save signal recomputes everyone's points
    return Response(_admin_match_dict(match))


# --------------------------------------------------------------------------- #
# In-app admin: enter a member's tournament-wide bonus predictions on their
# behalf (gated to admins). Deliberately bypasses the per-league bonus lock —
# it's an admin override for entering picks collected offline.
# --------------------------------------------------------------------------- #
def _admin_bonus_member(membership, preds_by_mem):
    picks = {p.kind: _bonus_pick_value(p, p.kind) for p in preds_by_mem.get(membership.id, [])}
    return {
        "membership_id": membership.id,
        "name": membership.user.public_name,
        "picks": picks,
        "count": len(picks),
        "completed": len(picks) >= len(consts.BONUS_KIND_ORDER),
    }


@api_view(["GET"])
def admin_bonus_leagues(request):
    if not _is_admin(request.user):
        raise PermissionDenied(consts.MSG_ADMIN_ONLY)
    total_q = len(consts.BONUS_KIND_ORDER)
    out = []
    for league in League.objects.select_related("competition").order_by("name"):
        member_ids = list(Membership.objects.filter(league=league).values_list("id", flat=True))
        counts = {}
        for mid in BonusPrediction.objects.filter(
                membership__league=league).values_list("membership_id", flat=True):
            counts[mid] = counts.get(mid, 0) + 1
        out.append({
            "slug": league.slug,
            "name": league.name,
            "competition": league.competition.name,
            "member_count": len(member_ids),
            "bonus_enabled": league.bonus_enabled,
            "completed_count": sum(1 for mid in member_ids if counts.get(mid, 0) >= total_q),
        })
    return Response(out)


def _admin_bonus_payload(league):
    competition = league.competition
    memberships = list(Membership.objects.filter(league=league).select_related("user"))
    preds_by_mem = {}
    for p in BonusPrediction.objects.filter(membership__league=league):
        preds_by_mem.setdefault(p.membership_id, []).append(p)
    return {
        "slug": league.slug,
        "name": league.name,
        "bonus_enabled": league.bonus_enabled,
        "lock_at": league.bonus_lock_at.isoformat() if league.bonus_lock_at else None,
        "is_open": league.bonus_is_open(),
        "questions": [
            {
                "kind": kind,
                "label": consts.BONUS_KIND_LABELS[kind],
                "answer_type": consts.BONUS_ANSWER_TYPE[kind],
                "points": league.bonus_points_for(kind),
            }
            for kind in consts.BONUS_KIND_ORDER
        ],
        "teams": [_team(t) for t in competition.teams.order_by("group", "name_fa")],
        "players": [
            _player_candidate(pc)
            for pc in competition.player_candidates.select_related("team").all()
        ],
        "members_options": [
            {"id": m.id, "name": m.user.public_name} for m in memberships
        ],
        "members": [_admin_bonus_member(m, preds_by_mem) for m in memberships],
    }


def _admin_submit_bonus(request, league):
    membership = get_object_or_404(
        Membership, id=request.data.get("membership_id"), league=league)
    items = request.data.get("picks", [])
    if not isinstance(items, list):
        raise ValidationError({"picks": consts.MSG_BONUS_BAD_FORMAT})

    competition = league.competition
    saved = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if kind not in consts.BONUS_POINTS_FIELD:
            continue
        value = item.get("value")
        if value in (None, "", 0):
            BonusPrediction.objects.filter(membership=membership, kind=kind).delete()
            saved += 1
            continue
        answer_type = consts.BONUS_ANSWER_TYPE[kind]
        obj = _resolve_bonus_value(answer_type, value, competition, league)
        if obj is None:
            continue
        defaults = {"team": None, "player": None, "target_membership": None}
        if answer_type == consts.BonusAnswerType.TEAM:
            defaults["team"] = obj
        elif answer_type == consts.BonusAnswerType.PLAYER:
            defaults["player"] = obj
        else:
            defaults["target_membership"] = obj
        BonusPrediction.objects.update_or_create(
            membership=membership, kind=kind, defaults=defaults)
        saved += 1

    preds = {}
    for p in BonusPrediction.objects.filter(membership=membership):
        preds.setdefault(membership.id, []).append(p)
    return Response({"saved": saved, "member": _admin_bonus_member(membership, preds)})


@api_view(["GET", "POST"])
def admin_league_bonus(request, slug):
    """Admin: read every member's bonus picks for a league, or POST to set one
    member's picks. Body: {"membership_id", "picks": [{"kind", "value"}, ...]}.
    Bypasses the bonus lock on purpose (admin entering picks on a member's behalf)."""
    if not _is_admin(request.user):
        raise PermissionDenied(consts.MSG_ADMIN_ONLY)
    league = get_object_or_404(League, slug=slug)
    if request.method == "POST":
        return _admin_submit_bonus(request, league)
    return Response(_admin_bonus_payload(league))
