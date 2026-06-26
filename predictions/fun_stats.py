"""
Fun / novelty statistics for a league — all computed in Python from the
Prediction rows, nothing persisted. Returned as plain dicts for the API.

Eight stats:
  1. most_active     — who submitted the most predictions (%)
  2. dream_goals     — highest avg total goals predicted per match
  3. lone_wolf       — most unique picks no other member made
  4. best_buddies    — pairs of members whose picks agree most
  5. draw_kings      — most draws predicted
  6. crowd_favorites — most popular predicted scorelines
  7. sheep_goat      — % of picks matching the crowd consensus for each match
  8. boldest         — largest average predicted margin (goal difference)
"""
from collections import Counter, defaultdict

from . import consts


def build_fun_stats(league, viewer_user_id):
    from .models import Membership, Prediction

    memberships = list(
        Membership.objects.filter(league=league).select_related("user")
    )
    if not memberships:
        return {"has_data": False}

    mem_by_id = {m.id: m for m in memberships}
    member_ids = [m.id for m in memberships]

    predictions = list(
        Prediction.objects.filter(membership__league=league)
        .only("membership_id", "match_id", "predicted_home", "predicted_away")
    )
    if not predictions:
        return {"has_data": False}

    by_member = defaultdict(list)
    for p in predictions:
        by_member[p.membership_id].append(p)

    by_match = defaultdict(list)
    for p in predictions:
        by_match[p.match_id].append(p)

    def _name(mid):
        m = mem_by_id.get(mid)
        return m.user.public_name if m else "؟"

    def _is_me(mid):
        m = mem_by_id.get(mid)
        return bool(m and m.user_id == viewer_user_id)

    def _row(mid, **extra):
        return {"name": _name(mid), "is_me": _is_me(mid), **extra}

    # ------------------------------------------------------------------ #
    # 1. Most active — prediction count + coverage %
    # ------------------------------------------------------------------ #
    total_matches = len(by_match)
    most_active = sorted(
        [_row(mid, count=len(ps)) for mid, ps in by_member.items()],
        key=lambda r: -r["count"],
    )
    # Include members with zero predictions
    active_ids = {r["name"] for r in most_active}
    for mid in member_ids:
        if mid not in by_member:
            row = _row(mid, count=0)
            if row["name"] not in active_ids:
                most_active.append(row)

    # ------------------------------------------------------------------ #
    # 2. Dream goals — avg goals predicted (home + away) per match
    # ------------------------------------------------------------------ #
    dream_goals = sorted(
        [
            _row(mid, avg_goals=round(
                sum(p.predicted_home + p.predicted_away for p in ps) / len(ps), 1,
            ))
            for mid, ps in by_member.items()
        ],
        key=lambda r: -r["avg_goals"],
    )

    # ------------------------------------------------------------------ #
    # 3. Lone wolf — picks that no other member made for the same match
    # ------------------------------------------------------------------ #
    lone_counts = Counter()
    for match_id, preds in by_match.items():
        score_freq = Counter((p.predicted_home, p.predicted_away) for p in preds)
        for p in preds:
            if score_freq[(p.predicted_home, p.predicted_away)] == 1:
                lone_counts[p.membership_id] += 1

    lone_wolf = sorted(
        [_row(mid, count=lone_counts.get(mid, 0)) for mid in by_member],
        key=lambda r: -r["count"],
    )

    # ------------------------------------------------------------------ #
    # 4. Best buddies — top pairs by exact prediction agreement
    # ------------------------------------------------------------------ #
    buddy_rows = []
    for i, mid_a in enumerate(member_ids):
        for mid_b in member_ids[i + 1:]:
            # .get() (not by_member[mid]) — indexing a defaultdict would insert an
            # empty list for members who never predicted, and later sections divide
            # by len(ps), hitting ZeroDivisionError.
            picks_a = {p.match_id: (p.predicted_home, p.predicted_away) for p in by_member.get(mid_a, [])}
            picks_b = {p.match_id: (p.predicted_home, p.predicted_away) for p in by_member.get(mid_b, [])}
            shared = set(picks_a.keys()) & set(picks_b.keys())
            # Require a floor of shared predictions: otherwise a pair that
            # matched on its single overlapping game shows up at 100% and
            # crowds out genuinely similar members.
            if len(shared) < consts.FUN_STATS_MIN_BUDDY_MATCHES:
                continue
            match_count = sum(1 for m in shared if picks_a[m] == picks_b[m])
            buddy_rows.append({
                "name_a": _name(mid_a),
                "is_me_a": _is_me(mid_a),
                "name_b": _name(mid_b),
                "is_me_b": _is_me(mid_b),
                "match_count": match_count,
                "total": len(shared),
                "pct": round(match_count / len(shared) * 100, 1),
            })

    best_buddies = sorted(buddy_rows, key=lambda r: (-r["pct"], -r["match_count"]))[:5]

    # ------------------------------------------------------------------ #
    # 5. Draw kings — most draws predicted (home == away)
    # ------------------------------------------------------------------ #
    draw_cnt = Counter()
    for p in predictions:
        if p.predicted_home == p.predicted_away:
            draw_cnt[p.membership_id] += 1

    draw_kings = sorted(
        [
            _row(mid, count=draw_cnt.get(mid, 0), pct=round(
                draw_cnt.get(mid, 0) / len(ps) * 100, 1,
            ))
            for mid, ps in by_member.items()
        ],
        key=lambda r: -r["count"],
    )

    # ------------------------------------------------------------------ #
    # 6. Crowd favorites — most predicted scorelines
    # ------------------------------------------------------------------ #
    score_freq = Counter((p.predicted_home, p.predicted_away) for p in predictions)
    crowd_favorites = [
        {"home": h, "away": a, "count": c}
        for (h, a), c in score_freq.most_common(10)
    ]

    # ------------------------------------------------------------------ #
    # 7. Sheep vs Goat — agreement rate with the crowd consensus per match
    #    Only counts matches where at least 2 members predicted.
    # ------------------------------------------------------------------ #
    sg_rows = []
    for mid, ps in by_member.items():
        hits, total = 0, 0
        for p in ps:
            match_preds = by_match[p.match_id]
            if len(match_preds) < 2:
                continue
            modal = Counter(
                (q.predicted_home, q.predicted_away) for q in match_preds
            ).most_common(1)[0][0]
            if (p.predicted_home, p.predicted_away) == modal:
                hits += 1
            total += 1
        if total > 0:
            sg_rows.append(_row(mid, pct=round(hits / total * 100, 1)))

    sheep_goat = sorted(sg_rows, key=lambda r: -r["pct"])

    # ------------------------------------------------------------------ #
    # 8. Boldest — largest average predicted margin (|home - away|)
    # ------------------------------------------------------------------ #
    boldest = sorted(
        [
            _row(mid, avg_margin=round(
                sum(abs(p.predicted_home - p.predicted_away) for p in ps) / len(ps), 1,
            ))
            for mid, ps in by_member.items()
        ],
        key=lambda r: -r["avg_margin"],
    )

    return {
        "has_data": True,
        "total_predictions": len(predictions),
        "member_count": len(memberships),
        "total_matches": total_matches,
        "most_active": most_active,
        "dream_goals": dream_goals,
        "lone_wolf": lone_wolf,
        "best_buddies": best_buddies,
        "draw_kings": draw_kings,
        "crowd_favorites": crowd_favorites,
        "sheep_goat": sheep_goat,
        "boldest": boldest,
    }
