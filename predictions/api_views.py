from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from . import consts, scoring
from .models import Competition, League, Match, Membership, Prediction
from .throttles import JOIN_LEAGUE_THROTTLES, PREDICT_THROTTLES


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


def _league_dict(league, membership):
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
@api_view(["GET"])
def me(request):
    user = request.user
    return Response({
        "email": user.email,
        "display_name": user.display_name,
        "public_name": user.public_name,
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
    return Response(_league_dict(league, membership), status=201)


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


@api_view(["GET"])
def league_detail(request, slug):
    membership = _get_membership(request, slug)
    return Response(_league_dict(membership.league, membership))


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
    rows = scoring.leaderboard(membership.league)
    data = [
        {
            "rank": row["rank"],
            "name": row["name"],
            "total": float(row["total"]),
            "played": row["played"],
            "exact_count": row["exact_count"],
            "is_me": row["membership"].user_id == request.user.id,
        }
        for row in rows
    ]
    return Response(data)


@api_view(["GET"])
def match_detail(request, slug, match_id):
    membership = _get_membership(request, slug)
    league = membership.league
    match = get_object_or_404(Match, id=match_id, competition=league.competition)
    now = timezone.now()

    revealed = not match.is_open_for(league.lock_minutes, now)
    others = []
    if revealed:
        scores = {s.membership_id: s for s in match.scores.all()}
        qs = (
            Prediction.objects.filter(match=match, membership__league=league)
            .select_related("membership", "membership__user")
        )
        for p in qs:
            s = scores.get(p.membership_id)
            others.append({
                "name": p.membership.user.public_name,
                "home": p.predicted_home,
                "away": p.predicted_away,
                "points": float(s.points) if s else None,
                "tier_label": consts.TIER_LABELS.get(s.tier) if s else None,
                "is_me": p.membership_id == membership.id,
            })

    my_pred = Prediction.objects.filter(membership=membership, match=match).first()
    return Response({
        "match": _match_dict(match, league, now, my_pred),
        "revealed": revealed,
        "lock_time": match.lock_time(league.lock_minutes).isoformat(),
        "predictions": others,
    })
