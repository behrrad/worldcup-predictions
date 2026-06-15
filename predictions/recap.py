"""
Matchday recap — the data behind the end-of-day "story".

A *matchday* is a calendar day (in settings.TIME_ZONE) on which at least one
match finished. For one league and one matchday this module computes:

  * the day's results,
  * a personal summary for the viewer (points, hit breakdown, best call, and
    how their leaderboard rank moved across the day), and
  * league-wide superlatives (top scorer, best single call, the day's biggest
    upset, the biggest rank climber) plus the standings after the day.

It returns rich Python objects (Membership / Match / MatchScore / Prediction and
Decimals); the API layer turns those into JSON, so all Persian labels stay in
consts and out of here. Read-only: nothing is persisted.
"""
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from django.utils import timezone

from . import consts
from .models import Match, MatchScore, Membership, Prediction

_ZERO = Decimal("0.00")
# Tiers that mean the winner was called right (the prediction "hit").
_CORRECT_TIERS = {consts.Tier.EXACT, consts.Tier.DIFF, consts.Tier.WINNER}


def _local_date(dt):
    """The calendar date of an instant in the project's timezone."""
    return timezone.localtime(dt).date()


def _zero_dict():
    return defaultdict(lambda: _ZERO)


def _rank(totals, memberships):
    """Map membership_id -> rank for the given totals.

    Standard competition ranking (ties share a rank), tie-broken by join time —
    the same rule scoring.leaderboard uses, so a recap rank matches the board.
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


def _best_score(scores):
    """The most impressive of a member's day scores: most points, then by tier.

    `scores` is a list of (MatchScore, Match, Prediction). Only entries the
    member actually predicted are passed in. Returns the winning tuple or None.
    """
    if not scores:
        return None
    return max(
        scores,
        key=lambda t: (t[0].points, t[0].tier == consts.Tier.EXACT),
    )


def available_dates(competition):
    """Ascending ISO dates (YYYY-MM-DD) that have at least one finished match."""
    finished = Match.objects.filter(
        competition=competition, status=consts.MatchStatus.FINISHED,
    ).only("kickoff")
    dates = sorted({_local_date(m.kickoff) for m in finished})
    return [d.strftime(consts.RECAP_DATE_FORMAT) for d in dates]


def build_recap(league, viewer_membership, date_str=None):
    """Assemble the recap for one league + matchday.

    `date_str` (YYYY-MM-DD) selects the matchday; an unknown/missing value falls
    back to the most recent finished day. Returns a dict the API layer
    serializes — see module docstring for the shape. When no match has finished
    yet, `date` is None and the day-specific sections are empty.
    """
    competition = league.competition
    finished = list(
        Match.objects.filter(
            competition=competition, status=consts.MatchStatus.FINISHED,
        ).select_related("home_team", "away_team")
    )
    match_date = {m.id: _local_date(m.kickoff) for m in finished}
    dates = sorted({d.strftime(consts.RECAP_DATE_FORMAT) for d in match_date.values()})

    if not dates:
        return {"date": None, "available_dates": [], "matches": [],
                "me": None, "general": None}

    target = date_str if date_str in dates else dates[-1]
    target_date = datetime.strptime(target, consts.RECAP_DATE_FORMAT).date()
    day_matches = sorted(
        (m for m in finished if match_date[m.id] == target_date),
        key=lambda m: (m.kickoff, m.match_number or 0),
    )
    day_match_ids = {m.id for m in day_matches}

    memberships = list(Membership.objects.filter(league=league).select_related("user"))

    # One pass over the league's scores: cumulative totals through the previous
    # day (before) and through this day (after), plus this day's scores.
    before, after = _zero_dict(), _zero_dict()
    day_scores = {}  # (membership_id, match_id) -> MatchScore
    day_points = _zero_dict()
    for s in MatchScore.objects.filter(membership__league=league):
        d = match_date.get(s.match_id)
        if d is None:
            continue
        if d < target_date:
            before[s.membership_id] += s.points
            after[s.membership_id] += s.points
        elif d == target_date:
            after[s.membership_id] += s.points
            day_scores[(s.membership_id, s.match_id)] = s
            day_points[s.membership_id] += s.points

    day_preds = {
        (p.membership_id, p.match_id): p
        for p in Prediction.objects.filter(
            membership__league=league, match_id__in=day_match_ids,
        )
    }
    rank_before = _rank(before, memberships)
    rank_after = _rank(after, memberships)

    # Per-member day summary, reused by both the personal and the general views.
    summaries = {}
    for m in memberships:
        hits = {t: 0 for t in
                (consts.Tier.EXACT, consts.Tier.DIFF, consts.Tier.WINNER,
                 consts.Tier.PARTICIPATION, consts.Tier.NONE)}
        predicted = []  # (MatchScore, Match, Prediction) for matches they called
        for match in day_matches:
            s = day_scores.get((m.id, match.id))
            if s is None:
                continue  # no score row (e.g. joined after the match) — skip
            p = day_preds.get((m.id, match.id))
            if p is None:
                hits[consts.Tier.NONE] += 1  # finished but no prediction = a miss
            else:
                hits[s.tier] += 1
                predicted.append((s, match, p))
        summaries[m.id] = {
            "points": day_points.get(m.id, _ZERO),
            "hits": hits,
            "predicted": predicted,
            "best": _best_score(predicted),
        }

    participants = [m for m in memberships if summaries[m.id]["predicted"]]
    day_total = sum((summaries[m.id]["points"] for m in participants), _ZERO)
    day_avg = (day_total / len(participants)) if participants else _ZERO
    top_points = max((summaries[m.id]["points"] for m in memberships), default=_ZERO)

    me = _viewer_recap(
        viewer_membership, day_matches, summaries,
        before, after, rank_before, rank_after, top_points, day_avg,
    )
    general = _general_recap(
        memberships, day_matches, day_match_ids, summaries, day_scores, day_preds,
        rank_before, rank_after, after, top_points,
    )
    return {
        "date": target,
        "available_dates": dates,
        "matches": [
            {"match": m, "predicted_count": _predicted_count(m.id, day_preds)}
            for m in day_matches
        ],
        "me": me,
        "general": general,
    }


def _predicted_count(match_id, day_preds):
    return sum(1 for (_, mid) in day_preds if mid == match_id)


def _viewer_recap(membership, day_matches, summaries, before, after,
                  rank_before, rank_after, top_points, day_avg):
    """The "your day" section for the requesting member."""
    summary = summaries.get(membership.id)
    if summary is None:  # not actually a member of this league (shouldn't happen)
        return None
    points = summary["points"]
    r_before, r_after = rank_before[membership.id], rank_after[membership.id]
    return {
        "membership": membership,
        "participated": bool(summary["predicted"]),
        "predicted": len(summary["predicted"]),
        "total": len(day_matches),
        "points": points,
        "hits": summary["hits"],
        "best": summary["best"],
        "rank_before": r_before,
        "rank_after": r_after,
        # Positive = climbed the table across the day.
        "rank_delta": r_before - r_after,
        "total_before": before.get(membership.id, _ZERO),
        "total_after": after.get(membership.id, _ZERO),
        "is_top_scorer": points > _ZERO and points >= top_points,
        "day_avg": day_avg,
    }


def _general_recap(memberships, day_matches, day_match_ids, summaries, day_scores,
                   day_preds, rank_before, rank_after, after, top_points):
    """The league-wide superlatives for the matchday."""
    # Top scorer of the day (with a count of anyone tied with them).
    top_scorer = None
    if top_points > _ZERO:
        leaders = [m for m in memberships if summaries[m.id]["points"] == top_points]
        top_scorer = {"membership": leaders[0], "points": top_points,
                      "ties": len(leaders) - 1}

    # Best single call of the day: most points, breaking ties toward the rarer
    # feat (fewest other members who reached the same tier on that match).
    tier_counts = defaultdict(lambda: defaultdict(int))  # match_id -> tier -> n
    for (mid, match_id), s in day_scores.items():
        if (mid, match_id) in day_preds:
            tier_counts[match_id][s.tier] += 1
    best_call = None
    best_key = None
    for m in memberships:
        cand = summaries[m.id]["best"]
        if cand is None:
            continue
        s, match, pred = cand
        also = tier_counts[match.id][s.tier] - 1  # others who matched this tier
        key = (s.points, -also)  # more points, then fewer who also did it
        if best_key is None or key > best_key:
            best_key = key
            best_call = {"membership": m, "match": match, "score": s,
                         "prediction": pred, "also_count": also}

    # Upset of the day: the match the fewest people called the winner on.
    surprise = None
    best_ratio = None
    for match in day_matches:
        predicted_n = _predicted_count(match.id, day_preds)
        if predicted_n == 0:
            continue
        correct = sum(
            1 for m in memberships
            if (s := day_scores.get((m.id, match.id))) and s.tier in _CORRECT_TIERS
        )
        ratio = correct / predicted_n
        if best_ratio is None or ratio < best_ratio:
            best_ratio = ratio
            surprise = {"match": match, "correct_count": correct,
                        "predicted_count": predicted_n}

    # Biggest climber: largest positive rank change across the day.
    mover = None
    best_delta = 0
    for m in memberships:
        delta = rank_before[m.id] - rank_after[m.id]
        if delta > best_delta:
            best_delta = delta
            mover = {"membership": m, "from_rank": rank_before[m.id],
                     "to_rank": rank_after[m.id], "delta": delta}

    # Closing podium: current standings (after the day), top N.
    podium_members = sorted(
        memberships, key=lambda m: (rank_after[m.id], m.joined_at),
    )[:consts.RECAP_PODIUM_SIZE]
    podium = [
        {"membership": m, "rank": rank_after[m.id], "total": after.get(m.id, _ZERO)}
        for m in podium_members
    ]

    return {"top_scorer": top_scorer, "best_call": best_call,
            "surprise": surprise, "mover": mover, "podium": podium}
