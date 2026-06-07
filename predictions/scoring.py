"""
Scoring engine.

A prediction earns the single highest tier that applies, then the result is
multiplied by the league's per-stage multiplier:

    exact score ............... points_exact            (default 10)
    right winner + right diff . points_correct_diff     (default 7)
    right winner only ......... points_correct_winner   (default 5)
    submitted but wrong ....... points_participation    (default 2)
    no prediction ............. 0

    final = base * stage_multiplier   (group ×1.0, knockout ×1.5 by default)

All the numbers above are league settings, editable in the admin.
"""
from decimal import ROUND_HALF_UP, Decimal

from . import consts

_CENTS = Decimal("0.01")


def outcome_sign(home: int, away: int) -> int:
    """1 if the home side wins, -1 if the away side wins, 0 for a draw."""
    if home > away:
        return 1
    if home < away:
        return -1
    return 0


def base_tier(predicted_home, predicted_away, actual_home, actual_away) -> str:
    """Which scoring tier a submitted prediction falls into."""
    if predicted_home == actual_home and predicted_away == actual_away:
        return consts.Tier.EXACT
    # Equal goal difference implies the same winner *and* margin (draws: 0 == 0).
    if (predicted_home - predicted_away) == (actual_home - actual_away):
        return consts.Tier.DIFF
    if outcome_sign(predicted_home, predicted_away) == outcome_sign(actual_home, actual_away):
        return consts.Tier.WINNER
    return consts.Tier.PARTICIPATION


def base_points_for_tier(league, tier: str) -> int:
    """Map a tier to the league's configured base points."""
    return {
        consts.Tier.EXACT: league.points_exact,
        consts.Tier.DIFF: league.points_correct_diff,
        consts.Tier.WINNER: league.points_correct_winner,
        consts.Tier.PARTICIPATION: league.points_participation,
        consts.Tier.NONE: consts.POINTS_NO_PREDICTION,
    }[tier]


def score_prediction(league, match, prediction):
    """
    Compute (Decimal points, tier) for one member's prediction on a finished
    match. `prediction` may be None when nothing was submitted in time.
    Returns None if the match has no final result yet.
    """
    if not match.is_finished:
        return None

    if prediction is None:
        return Decimal("0.00"), consts.Tier.NONE

    tier = base_tier(
        prediction.predicted_home, prediction.predicted_away,
        match.home_score, match.away_score,
    )
    base = Decimal(base_points_for_tier(league, tier))
    multiplier = Decimal(league.multiplier_for(match.stage))
    points = (base * multiplier).quantize(_CENTS, rounding=ROUND_HALF_UP)
    return points, tier


# --------------------------------------------------------------------------- #
# Recompute helpers — keep MatchScore rows in sync with results & settings
# --------------------------------------------------------------------------- #
def _upsert_scores_for(match, memberships, league):
    """Create/update MatchScore rows for the given memberships of one league."""
    from .models import MatchScore, Prediction

    predictions = {
        p.membership_id: p
        for p in Prediction.objects.filter(match=match, membership__league=league)
    }
    written = 0
    for membership in memberships:
        result = score_prediction(league, match, predictions.get(membership.id))
        if result is None:
            continue
        points, tier = result
        MatchScore.objects.update_or_create(
            membership=membership, match=match,
            defaults={"points": points, "tier": tier},
        )
        written += 1
    return written


def recompute_match_scores(match) -> int:
    """
    Recompute every member's score for a single match across all leagues that
    predict this competition. Called whenever a result is entered/changed.
    """
    from .models import League, MatchScore, Membership

    if not match.is_finished:
        # Result was removed/incomplete: drop any stale scores for this match.
        MatchScore.objects.filter(match=match).delete()
        return 0

    written = 0
    for league in League.objects.filter(competition=match.competition):
        memberships = list(Membership.objects.filter(league=league))
        written += _upsert_scores_for(match, memberships, league)
    return written


def recompute_league_scores(league) -> int:
    """Recompute all scores for one league (used after its settings change)."""
    from .models import Match, Membership

    memberships = list(Membership.objects.filter(league=league))
    finished = Match.objects.filter(
        competition=league.competition, status=consts.MatchStatus.FINISHED
    )
    written = 0
    for match in finished:
        if match.is_finished:
            written += _upsert_scores_for(match, memberships, league)
    return written


def leaderboard(league):
    """
    Return a list of dicts ranked by total points, ready for the template:
        [{"rank", "membership", "name", "total", "played", "exact_count"}, ...]
    """
    from django.db.models import Count, Q, Sum
    from .models import Membership

    rows = (
        Membership.objects.filter(league=league)
        .select_related("user")
        .annotate(
            total=Sum("scores__points"),
            played=Count("scores", filter=Q(scores__tier__isnull=False)),
            exact_count=Count("scores", filter=Q(scores__tier=consts.Tier.EXACT)),
        )
        .order_by("-total", "joined_at")
    )

    table = []
    rank = 0
    prev_total = object()
    for i, m in enumerate(rows, start=1):
        total = m.total or Decimal("0.00")
        # Standard competition ranking (ties share a rank).
        if total != prev_total:
            rank = i
            prev_total = total
        table.append({
            "rank": rank,
            "membership": m,
            "name": m.user.public_name,
            "total": total,
            "played": m.played or 0,
            "exact_count": m.exact_count or 0,
        })
    return table
