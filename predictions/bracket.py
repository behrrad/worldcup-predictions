"""
Knockout bracket auto-advance.

Every knockout match is seeded with team-less slots that name where the team
comes from — ``home_label``/``away_label`` like "Match 73 Winner" (or "… Loser"
for the third-place game). This module reads those references straight from the
schedule JSON (`predictions/data/worldcup2026.json`) and, once a feeding match is
finished, drops the advancing (or eliminated) side into the slot it feeds.

It is fully self-contained: it consults only our own finalized results, so each
round populates itself as the previous round ends — no external feed, no manual
step. `advance_bracket` runs on every tick (see `telegram.run_tick`); it's a
cheap no-op once every slot is filled.

Slots are written with ``queryset.update()`` — never ``save()`` — so filling a
team is not a result: it triggers no scoring recompute and never disturbs the
predictions already placed on that fixture (a knockout match can't finalize
until it has both teams anyway; see `results_sync.apply_results`).
"""
import json
import logging
from pathlib import Path

from django.conf import settings
from django.db.models import Q

from . import consts, seed_data as sd

logger = logging.getLogger(__name__)

_DATA_PATH = Path(settings.BASE_DIR) / "predictions" / "data" / "worldcup2026.json"
_edges_cache = None


def load_bracket_edges(path=None):
    """Return the bracket wiring from the schedule JSON:

        {match_number: {"home": (src_match_number, kind) | None,
                        "away": (src_match_number, kind) | None}}

    where kind is consts.BRACKET_WINNER / BRACKET_LOSER. Only matches that
    reference an earlier match on at least one side are included (group-stage and
    R32 fixtures name teams/groups, not matches, so they're skipped). The default
    (WC) file is parsed once and cached; an explicit path is always re-read.
    """
    global _edges_cache
    if path is None and _edges_cache is not None:
        return _edges_cache

    with open(path or _DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)

    edges = {}
    for match in data.get("matches", []):
        number = match.get("match_number")
        home = consts.parse_bracket_slot(match.get("home_label"))
        away = consts.parse_bracket_slot(match.get("away_label"))
        if number and (home or away):
            edges[number] = {consts.SIDE_HOME: home, consts.SIDE_AWAY: away}

    if path is None:
        _edges_cache = edges
    return edges


def _resolved_team_id(source, kind):
    """The team id that advances (BRACKET_WINNER) or is eliminated
    (BRACKET_LOSER) from a finished source match, or None if it isn't decided
    yet (unfinished, or a draw not yet settled on penalties)."""
    side = source.advancing_side  # Advancer.HOME / AWAY / NONE("")
    if side == consts.Advancer.HOME:
        winner_id, loser_id = source.home_team_id, source.away_team_id
    elif side == consts.Advancer.AWAY:
        winner_id, loser_id = source.away_team_id, source.home_team_id
    else:
        return None
    return winner_id if kind == consts.BRACKET_WINNER else loser_id


def advance_bracket(competition, edges=None):
    """Fill every empty knockout slot whose feeding match has finished.

    Returns the number of team slots filled (0 when there's nothing to do).
    Idempotent: a slot that already holds a team is never touched, so re-running
    only ever fills newly-decided slots. Auto-runs for the World Cup only (its
    edges come from the WC schedule); pass `edges` explicitly to drive it for
    any competition (used by tests).
    """
    from .models import Match

    if edges is None and competition.slug != sd.WC2026_SLUG:
        return 0

    open_slots = list(
        Match.objects.filter(competition=competition, stage__in=consts.KNOCKOUT_STAGES)
        .filter(Q(home_team__isnull=True) | Q(away_team__isnull=True))
    )
    if not open_slots:
        return 0

    if edges is None:
        edges = load_bracket_edges()
    by_number = {
        m.match_number: m
        for m in Match.objects.filter(competition=competition)
    }

    filled = 0
    for target in open_slots:
        edge = edges.get(target.match_number)
        if not edge:
            continue
        updates = {}
        for side in (consts.SIDE_HOME, consts.SIDE_AWAY):
            if getattr(target, f"{side}_team_id") is not None:
                continue  # slot already decided — leave it
            ref = edge.get(side)
            if not ref:
                continue
            source = by_number.get(ref[0])
            if source is None or not source.is_finished:
                continue
            team_id = _resolved_team_id(source, ref[1])
            if team_id is not None:
                updates[f"{side}_team_id"] = team_id
        if updates:
            # queryset.update(): fill the teams without a save() (no scoring, no
            # touching predictions on this fixture).
            Match.objects.filter(pk=target.pk).update(**updates)
            filled += len(updates)
            logger.info(
                "bracket: filled match %s slots %s",
                target.match_number, sorted(updates),
            )
    return filled
