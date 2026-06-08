"""
Per-league results spreadsheet (.xlsx) builder.

The layout mirrors the shared league template: row 1 holds the league title plus
every member's name, row 2 holds each member's running total, and from row 3 on
there is one row per match. Columns A–D carry the fixture (home, away, actual
home, actual away); each member then owns three columns — predicted home,
predicted away, points.

The one rule worth stating loudly: a match's row stays blank (no result, picks
or points) until its lock time has passed, so a downloaded file can never leak an
upcoming pick. Reveal keys strictly off the lock time — not off whether a result
has been entered — so even an early-entered result can't expose a pick before the
match locks.
"""
from decimal import Decimal
from io import BytesIO

from django.utils import timezone
from openpyxl import Workbook

from . import consts


def _member_columns(index):
    """Return (home_col, away_col, points_col) for the member at a 0-based index."""
    base = consts.EXPORT_FIRST_MEMBER_COL + index * consts.EXPORT_COLS_PER_MEMBER
    return base, base + 1, base + 2


def _team_label(team, label):
    """Persian display name for a fixture side (bracket slot if team is undecided)."""
    if team:
        return team.name_fa
    return consts.bracket_label_fa(label)


def build_league_workbook(league, now=None):
    """Build and return an openpyxl Workbook of the league's results."""
    from .models import Match, MatchScore, Membership, Prediction

    now = now or timezone.now()

    memberships = list(
        Membership.objects.filter(league=league)
        .select_related("user")
        .order_by("joined_at")  # stable column order: members never reshuffle
    )
    member_index = {m.id: i for i, m in enumerate(memberships)}

    matches = list(
        Match.objects.filter(competition=league.competition)
        .select_related("home_team", "away_team")
        .order_by("kickoff", "match_number")
    )

    # A match is "revealed" strictly once its lock time has passed. Keying off the
    # lock time alone (not match.is_finished) means that even if a result is entered
    # early — before the match would normally lock — its picks, result and points
    # all stay hidden until lock. That's the rule that makes an upcoming prediction
    # truly invisible in the downloaded file.
    revealed_ids = {
        m.id for m in matches if now >= m.lock_time(league.lock_minutes)
    }

    # predictions[match_id][membership_id] -> Prediction
    predictions = {}
    for p in Prediction.objects.filter(membership__league=league):
        predictions.setdefault(p.match_id, {})[p.membership_id] = p

    # scores[match_id][membership_id] -> MatchScore, and each member's total.
    # Totals only sum scores from *revealed* matches, so the printed total always
    # equals the sum of the points cells actually shown below it (no hidden leak).
    scores = {}
    totals = {m.id: Decimal("0") for m in memberships}
    for s in MatchScore.objects.filter(membership__league=league):
        scores.setdefault(s.match_id, {})[s.membership_id] = s
        if s.match_id in revealed_ids:
            totals[s.membership_id] = totals.get(s.membership_id, Decimal("0")) + s.points

    wb = Workbook()
    ws = wb.active
    ws.title = (league.name or "")[:consts.EXPORT_SHEET_TITLE_MAX] or consts.EXPORT_SHEET_TITLE_FALLBACK

    # Row 1: league title (A1) + member names. Row 2: member totals.
    ws.cell(row=consts.EXPORT_TITLE_ROW, column=consts.EXPORT_COL_HOME, value=league.name)
    for m in memberships:
        home_col, _, _ = _member_columns(member_index[m.id])
        ws.cell(row=consts.EXPORT_TITLE_ROW, column=home_col, value=m.user.public_name)
        ws.cell(row=consts.EXPORT_TOTAL_ROW, column=home_col, value=float(totals[m.id]))

    # One row per match, in kickoff order.
    row = consts.EXPORT_FIRST_MATCH_ROW
    for match in matches:
        ws.cell(row=row, column=consts.EXPORT_COL_HOME,
                value=_team_label(match.home_team, match.home_label))
        ws.cell(row=row, column=consts.EXPORT_COL_AWAY,
                value=_team_label(match.away_team, match.away_label))

        # Not locked yet -> show only the fixture; no result, picks or points leak.
        if match.id not in revealed_ids:
            row += 1
            continue

        if match.is_finished:
            ws.cell(row=row, column=consts.EXPORT_COL_ACTUAL_HOME, value=match.home_score)
            ws.cell(row=row, column=consts.EXPORT_COL_ACTUAL_AWAY, value=match.away_score)

        match_preds = predictions.get(match.id, {})
        match_scores = scores.get(match.id, {})
        for m in memberships:
            home_col, away_col, pts_col = _member_columns(member_index[m.id])
            p = match_preds.get(m.id)
            if p:
                ws.cell(row=row, column=home_col, value=p.predicted_home)
                ws.cell(row=row, column=away_col, value=p.predicted_away)
            s = match_scores.get(m.id)
            if s:
                ws.cell(row=row, column=pts_col, value=float(s.points))
        row += 1

    return wb


def league_xlsx_bytes(league, now=None):
    """Serialize the league's results workbook to .xlsx bytes."""
    buf = BytesIO()
    build_league_workbook(league, now=now).save(buf)
    return buf.getvalue()
