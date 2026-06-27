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
_AVG = Decimal("0.0001")  # points-per-game average is shown to 4 decimals
_ZERO = Decimal("0.00")


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


def provisional_points(league, match, prediction, actual_home, actual_away):
    """
    (Decimal points, tier) a prediction would earn if the match ended
    actual_home–actual_away. `prediction` may be None when nothing was
    submitted in time. Used both for real results (via score_prediction)
    and for the live leaderboard, where the in-play score plays the result.
    """
    if prediction is None:
        return Decimal("0.00"), consts.Tier.NONE

    tier = base_tier(
        prediction.predicted_home, prediction.predicted_away,
        actual_home, actual_away,
    )
    base = Decimal(base_points_for_tier(league, tier))
    multiplier = Decimal(league.multiplier_for(match.stage))
    points = (base * multiplier).quantize(_CENTS, rounding=ROUND_HALF_UP)
    return points, tier


def score_prediction(league, match, prediction):
    """
    Compute (Decimal points, tier) for one member's prediction on a finished
    match. `prediction` may be None when nothing was submitted in time.
    Returns None if the match has no final result yet.
    """
    if not match.is_finished:
        return None
    return provisional_points(
        league, match, prediction, match.home_score, match.away_score,
    )


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
    from django.db.models.functions import Coalesce
    from .models import Membership

    # Coalesce the sum to 0 so members with no score rows order as zero rather
    # than NULL. On Postgres, NULL sorts first under "-total" (descending), which
    # would otherwise float scoreless members to the top of the leaderboard.
    rows = (
        Membership.objects.filter(league=league)
        .select_related("user")
        .annotate(
            total=Coalesce(Sum("scores__points"), Decimal("0.00")),
            # Only games the member actually predicted. A finished match writes a
            # MatchScore row for *every* member (tier=NONE for non-predictors),
            # so counting all rows would report total finished matches instead.
            played=Count("scores", filter=~Q(scores__tier=consts.Tier.NONE)),
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
    _annotate_averages(league, table)
    return table


def _annotate_averages(league, table):
    """Layer the "points per game" view onto each leaderboard row:

        avg_points        total points ÷ games predicted, to 4 decimals
                          (0 when the member has predicted nothing yet)
        eligible_for_avg  True once they've predicted at least half of the
                          finished matches so far — the average is noisy below
                          that, so the UI only ranks members who clear the bar
        avg_rank          rank among eligible members by avg_points (None if not)

    `played` (set in leaderboard()) is the games the member actually predicted;
    `finished_count` is the league-wide pool of finished matches it's measured
    against.
    """
    from .models import Match

    finished_count = Match.objects.filter(
        competition=league.competition,
        status=consts.MatchStatus.FINISHED,
    ).count()
    for row in table:
        played = row["played"]
        row["avg_points"] = (
            (row["total"] / played).quantize(_AVG, rounding=ROUND_HALF_UP)
            if played else Decimal("0.0000")
        )
        row["eligible_for_avg"] = (
            finished_count > 0
            and played >= finished_count * consts.MIN_FINISHED_PARTICIPATION_RATIO
        )
        row["avg_rank"] = None

    eligible = sorted(
        (r for r in table if r["eligible_for_avg"]),
        # Best average first; ties broken by more games predicted, then seniority.
        key=lambda r: (-r["avg_points"], -r["played"], r["membership"].joined_at),
    )
    rank = 0
    prev_avg = object()
    for i, row in enumerate(eligible, start=1):
        if row["avg_points"] != prev_avg:
            rank = i
            prev_avg = row["avg_points"]
        row["avg_rank"] = rank


# --------------------------------------------------------------------------- #
# Progression — every member's cumulative total & rank after each finished match
# --------------------------------------------------------------------------- #
def _ranks_for(totals, memberships):
    """Map membership_id -> rank for the given cumulative totals.

    Standard competition ranking (ties share a rank), tie-broken by join time —
    the same rule leaderboard() uses, so a progression rank matches the board.
    """
    ordered = sorted(
        memberships, key=lambda m: (-totals.get(m.id, _ZERO), m.joined_at),
    )
    ranks = {}
    rank = 0
    prev = object()
    for i, m in enumerate(ordered, start=1):
        total = totals.get(m.id, _ZERO)
        if total != prev:
            rank = i
            prev = total
        ranks[m.id] = rank
    return ranks


def progression(league):
    """
    Replay the leaderboard match by match. Returns (steps, players):

      steps   -> [Match, ...]            finished matches, in chronological order
      players -> [{"membership", "totals": [Decimal, ...], "ranks": [int, ...],
                   "match_points": [Decimal, ...], "played": [int, ...]}, ...]

    Every per-player list is aligned with `steps`: `totals[i]`/`ranks[i]` are the
    member's cumulative total and rank *after* the i-th finished match,
    `match_points[i]` is what they earned on that match alone, and `played[i]` is
    how many of the matches so far they actually predicted (the denominator the
    UI uses for the average-points-per-prediction view — non-predictions earn 0
    and are never counted). A member with no score row for a match contributes 0
    that step (same zero-fill as the leaderboard, so late joiners simply sit flat
    until their first scored match). Read-only — nothing here is persisted.
    """
    from .models import Match, MatchScore, Membership, Prediction

    finished = list(
        Match.objects.filter(
            competition=league.competition, status=consts.MatchStatus.FINISHED,
        )
        .select_related("home_team", "away_team")
        .order_by("kickoff", "match_number")
    )
    memberships = list(Membership.objects.filter(league=league).select_related("user"))

    # points[membership_id][match_id] -> Decimal earned on that match.
    points = {}
    for s in MatchScore.objects.filter(membership__league=league):
        points.setdefault(s.membership_id, {})[s.match_id] = s.points
    # The (membership, match) pairs that were actually predicted — the average's
    # denominator counts these, not finished-but-unpredicted games.
    predicted = set(
        Prediction.objects.filter(membership__league=league)
        .values_list("membership_id", "match_id")
    )

    series = {
        m.id: {"totals": [], "ranks": [], "match_points": [], "played": []}
        for m in memberships
    }
    running = {m.id: _ZERO for m in memberships}
    played = {m.id: 0 for m in memberships}
    for match in finished:
        step_points = {}
        for m in memberships:
            earned = points.get(m.id, {}).get(match.id, _ZERO)
            running[m.id] += earned
            if (m.id, match.id) in predicted:
                played[m.id] += 1
            step_points[m.id] = earned
        ranks = _ranks_for(running, memberships)
        for m in memberships:
            s = series[m.id]
            s["totals"].append(running[m.id])
            s["ranks"].append(ranks[m.id])
            s["match_points"].append(step_points[m.id])
            s["played"].append(played[m.id])

    players = [{"membership": m, **series[m.id]} for m in memberships]
    return finished, players


def user_average_series(user):
    """
    One user's running average points-per-prediction over time, pooled across
    ALL their leagues. Returns (steps, series):

      steps  -> [Match, ...]            finished matches the user predicted in at
                                        least one league, in chronological order
      series -> {"totals": [Decimal, ...], "played": [int, ...],
                 "averages": [Decimal, ...]}     (all aligned with `steps`)

    At step i every league counts as its own prediction: `played` sums the user's
    predicted games across leagues so far and `averages[i] = totals[i] / played[i]`
    is the pooled mean. Powers the profile chart, which is league-agnostic — the
    per-league, rank-based progression() doesn't apply to a single player. Only
    games the user actually predicted feed the average. Read-only.
    """
    from .models import MatchScore, Prediction

    predicted = set(
        Prediction.objects.filter(membership__user=user)
        .values_list("membership_id", "match_id")
    )
    rows = (
        MatchScore.objects.filter(
            membership__user=user, match__status=consts.MatchStatus.FINISHED,
        )
        .select_related("match", "match__home_team", "match__away_team")
    )

    # Pool each finished match's predicted scores across the user's leagues.
    by_match = {}
    for s in rows:
        if (s.membership_id, s.match_id) not in predicted:
            continue  # finished but unpredicted in this league — not an average input
        bucket = by_match.get(s.match_id)
        if bucket is None:
            bucket = by_match[s.match_id] = {"match": s.match, "sum": _ZERO, "count": 0}
        bucket["sum"] += s.points
        bucket["count"] += 1

    ordered = sorted(
        by_match.values(),
        key=lambda b: (b["match"].kickoff, b["match"].match_number or 0),
    )
    steps, totals, played, averages = [], [], [], []
    run_total, run_played = _ZERO, 0
    for b in ordered:
        run_total += b["sum"]
        run_played += b["count"]
        steps.append(b["match"])
        totals.append(run_total)
        played.append(run_played)
        averages.append(run_total / run_played)  # run_played >= 1 by construction
    return steps, {"totals": totals, "played": played, "averages": averages}


# --------------------------------------------------------------------------- #
# Live leaderboard — in-play scores played as if they were the final result
# --------------------------------------------------------------------------- #
def _fetch_live_data(league):
    """Returns (live_matches, predictions_map) — shared by live_overlay and live_leaderboard."""
    from .models import Match, Prediction

    live_matches = list(
        Match.objects.select_related("home_team", "away_team")
        .filter(competition=league.competition)
        .exclude(live_status=consts.LiveStatus.NONE)
        .exclude(status=consts.MatchStatus.FINISHED)
        .filter(live_home_score__isnull=False, live_away_score__isnull=False)
    )
    if not live_matches:
        return [], {}
    predictions = {
        (p.membership_id, p.match_id): p
        for p in Prediction.objects.filter(
            match__in=live_matches, membership__league=league,
        )
    }
    return live_matches, predictions


def live_overlay(league):
    """
    Provisional extra points per membership from matches in play right now,
    treating the current live score as the final result. Returns
    {membership_id: Decimal} — empty when no match carries live state, so the
    caller knows there is nothing "live" to show. Display-only: nothing here
    is persisted, MatchScore rows still come only from official results.
    """
    from .models import Membership

    live_matches, predictions = _fetch_live_data(league)
    if not live_matches:
        return {}
    overlay = {}
    member_ids = Membership.objects.filter(league=league).values_list("id", flat=True)
    for membership_id in member_ids:
        total = Decimal("0.00")
        for match in live_matches:
            points, _tier = provisional_points(
                league, match, predictions.get((membership_id, match.id)),
                match.live_home_score, match.live_away_score,
            )
            total += points
        overlay[membership_id] = total
    return overlay


def live_leaderboard(league):
    """
    The official table with a live view layered on: every row also carries
    live_points (the provisional delta from in-play matches), live_total,
    live_rank, and live_picks (per-live-match predictions for that member).
    Returns (table, is_live, live_matches); when nothing is live the live_*
    fields simply mirror the official ones and live_matches is empty.
    """
    from .models import Membership

    table = leaderboard(league)
    live_matches, predictions = _fetch_live_data(league)

    overlay = {}
    if live_matches:
        member_ids = list(Membership.objects.filter(league=league).values_list("id", flat=True))
        for membership_id in member_ids:
            total = Decimal("0.00")
            for match in live_matches:
                points, _tier = provisional_points(
                    league, match, predictions.get((membership_id, match.id)),
                    match.live_home_score, match.live_away_score,
                )
                total += points
            overlay[membership_id] = total

    for row in table:
        mid = row["membership"].id
        delta = overlay.get(mid, Decimal("0.00"))
        row["live_points"] = delta
        row["live_total"] = row["total"] + delta
        row["live_picks"] = [
            {
                "match_id": m.id,
                "home": predictions[(mid, m.id)].predicted_home if (mid, m.id) in predictions else None,
                "away": predictions[(mid, m.id)].predicted_away if (mid, m.id) in predictions else None,
            }
            for m in live_matches
        ]

    ordered = sorted(
        table, key=lambda r: (-r["live_total"], r["membership"].joined_at),
    )
    rank = 0
    prev_total = object()
    for i, row in enumerate(ordered, start=1):
        if row["live_total"] != prev_total:
            rank = i
            prev_total = row["live_total"]
        row["live_rank"] = rank
    return table, bool(overlay), live_matches
