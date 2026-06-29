"""
Official results sync (football-data.org).

The single sanctioned pipeline that finalizes match results. It is used from
two places:

- the ``sync_results`` management command (manual / ad-hoc runs), and
- ``finalize_if_due`` — called lazily from the live API endpoint so a match
  gets its official result minutes after full time with **no cron** (free
  hosting), behind an atomic claim on ``Competition.results_checked_at``,
  exactly like the live-score refresh in ``live.py``.

Only matches the source reports as FINISHED with a full-time score are ever
applied, and they are applied through ``Match.save()`` on purpose: that is the
one path that finalizes a result and triggers the scoring recompute (via the
post_save signal). In-play provider data never comes through here — that's
``live.py``'s display-only territory.
"""
import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import consts, seed_data as sd

logger = logging.getLogger(__name__)


class ResultsFetchError(Exception):
    """football-data.org could not be fetched or returned unusable JSON."""


def _fetch(url, token):
    """GET a football-data.org URL and return parsed JSON (or raise)."""
    request = urllib.request.Request(url, headers={
        consts.FOOTBALL_DATA_TOKEN_HEADER: token,
        # The default "Python-urllib" User-Agent is rejected by some CDNs (see
        # the same gotcha in accounts/clerk.py), so send a real one.
        "User-Agent": consts.FOOTBALL_DATA_USER_AGENT,
    })
    try:
        with urllib.request.urlopen(request, timeout=consts.FOOTBALL_DATA_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise ResultsFetchError(consts.MSG_SYNC_HTTP_ERROR.format(error=exc))
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise ResultsFetchError(consts.MSG_SYNC_BAD_JSON)


def fetch_matches(token, source_code):
    """Fetch FINISHED matches for a competition from football-data.org (v4)."""
    return _fetch(
        f"{consts.FOOTBALL_DATA_BASE_URL}/competitions/{source_code}/matches"
        f"?status={consts.FOOTBALL_DATA_FINISHED}",
        token,
    )


def fetch_all_matches(token, source_code):
    """Fetch ALL matches for a competition (any status), so the knockout
    bracket — whose fixtures are only known once the draw is set — can be
    mirrored alongside the finished-result sync (see apply_bracket)."""
    return _fetch(
        f"{consts.FOOTBALL_DATA_BASE_URL}/competitions/{source_code}/matches",
        token,
    )


def normalize(payload):
    """Flatten the API payload to the fields we need, keeping only scored finals."""
    results = []
    for m in payload.get("matches", []):
        if m.get("status") != consts.FOOTBALL_DATA_FINISHED:
            continue
        full_time = (m.get("score") or {}).get("fullTime") or {}
        home, away = m.get("homeTeam") or {}, m.get("awayTeam") or {}
        if full_time.get("home") is None or full_time.get("away") is None:
            continue
        results.append({
            "home_code": home.get("tla"),
            "away_code": away.get("tla"),
            "home_name": (home.get("name") or "").strip().lower(),
            "away_name": (away.get("name") or "").strip().lower(),
            "home_score": full_time["home"],
            "away_score": full_time["away"],
            "utc_date": m.get("utcDate"),
        })
    return results


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _pick(candidates, utc_date, window_seconds):
    """From matches sharing a team pairing, pick the one closest to utc_date —
    but only if its kickoff is within window_seconds of it. Returns None when the
    date is unparseable or no candidate falls in the window (e.g. a same-team
    result from another season), so the caller treats it as unmatched."""
    when = _parse_dt(utc_date)
    if when is None:
        return None
    best = min(candidates, key=lambda m: abs((m.kickoff - when).total_seconds()))
    if abs((best.kickoff - when).total_seconds()) > window_seconds:
        return None
    return best


def apply_results(competition, results, dry_run=False):
    """Apply normalized FINISHED results onto the competition's schedule.

    Returns (updated, unchanged, unmatched, messages) where messages is a list
    of (logging level, text) pairs — the command prints them, the lazy path
    logs them. Saving a match fires the post_save signal that recomputes every
    member's points.
    """
    # Index local matches that have both teams, by code pairing and by
    # English-name pairing (the fallback for code mismatches).
    by_code, by_name = {}, {}
    for m in competition.matches.select_related("home_team", "away_team"):
        if m.home_team_id and m.away_team_id:
            by_code.setdefault((m.home_team.code, m.away_team.code), []).append(m)
            key = (m.home_team.name_en.strip().lower(),
                   m.away_team.name_en.strip().lower())
            by_name.setdefault(key, []).append(m)

    window = consts.FOOTBALL_DATA_MATCH_WINDOW_HOURS * 3600
    updated = unchanged = unmatched = 0
    messages = []

    with transaction.atomic():
        for r in results:
            candidates = (
                by_code.get((r["home_code"], r["away_code"]))
                or by_name.get((r["home_name"], r["away_name"]))
            )
            match = _pick(candidates, r["utc_date"], window) if candidates else None
            if match is None:
                # No local pairing, or the only match is too far from the source
                # date (likely a different season) — never apply it.
                unmatched += 1
                messages.append((logging.WARNING, consts.MSG_SYNC_UNMATCHED.format(
                    home=r["home_code"] or r["home_name"],
                    away=r["away_code"] or r["away_name"],
                    date=r["utc_date"],
                )))
                continue

            if (match.home_score == r["home_score"]
                    and match.away_score == r["away_score"]):
                unchanged += 1
                continue

            updated += 1
            messages.append((logging.INFO, consts.MSG_SYNC_UPDATED.format(
                n=match.match_number, home=match.home_team.name_fa,
                hs=r["home_score"], as_=r["away_score"], away=match.away_team.name_fa,
            )))
            if not dry_run:
                match.home_score = r["home_score"]
                match.away_score = r["away_score"]
                match.save()  # post_save signal recomputes scores

        if dry_run:
            transaction.set_rollback(True)

    return updated, unchanged, unmatched, messages


# --------------------------------------------------------------------------- #
# Knockout bracket mirror — copy decided fixtures onto our team-less slots
# --------------------------------------------------------------------------- #
# Our knockout matches ship with only bracket-slot labels ("Group A Winner",
# "Match 73 Winner") and no teams. Once the real bracket is set, football-data's
# WC feed reports each knockout fixture with its decided teams; we mirror those
# onto the matching local match so the result sync can then finalize it (it
# matches by team pairing, which needs both teams present). football-data has
# already advanced penalty-decided winners, so mirroring its bracket gives us
# the right teams in every round with no standings/penalty logic of our own.
def _team_index(competition):
    """code -> Team and english-name -> Team, for resolving feed teams."""
    by_code, by_name = {}, {}
    for team in competition.teams.all():
        if team.code:
            by_code[team.code] = team
        if team.name_en:
            by_name[team.name_en.strip().lower()] = team
    return by_code, by_name


def _resolve_team(by_code, by_name, code, name):
    """A feed team (tla + name) -> local Team, or None if it doesn't map.
    Exact match only, so placeholder slot names never resolve to a real team."""
    if code and code in by_code:
        return by_code[code]
    if name and name.strip().lower() in by_name:
        return by_name[name.strip().lower()]
    return None


def extract_fixtures(payload):
    """Knockout fixtures from the feed that have BOTH sides decided.

    Undecided slots come back with null/placeholder teams; those are filtered
    here (no usable tla/name) and again in apply_bracket (they don't resolve to
    a local Team), so a half-drawn bracket never assigns a wrong team.
    """
    fixtures = []
    for m in payload.get("matches", []):
        stage = consts.FOOTBALL_DATA_STAGE_MAP.get(m.get("stage"))
        if not stage:
            continue
        when = _parse_dt(m.get("utcDate"))
        if when is None:
            continue
        home, away = m.get("homeTeam") or {}, m.get("awayTeam") or {}
        if not (home.get("tla") or home.get("name")):
            continue
        if not (away.get("tla") or away.get("name")):
            continue
        fixtures.append({
            "stage": stage,
            "kickoff": when,
            "home_code": home.get("tla"),
            "away_code": away.get("tla"),
            "home_name": home.get("name") or "",
            "away_name": away.get("name") or "",
        })
    return fixtures


def apply_bracket(competition, fixtures, now=None):
    """Fill in teams on local knockout matches that are still missing one.

    Each feed fixture is matched to a local match of the same stage by nearest
    kickoff (greedy, one-to-one, within FOOTBALL_DATA_BRACKET_WINDOW_HOURS) and
    its teams copied in the feed's orientation — so a later FINISHED result in
    the same orientation matches by pairing. Teams are written with
    queryset.update() (never save()): assigning a team is not a result, so it
    must not flip the match to FINISHED, fire scoring, or touch predictions.

    Returns (assigned, messages) like apply_results.
    """
    from .models import Match

    now = now or timezone.now()
    local = list(
        Match.objects.filter(
            competition=competition, stage__in=consts.KNOCKOUT_STAGES
        ).filter(
            Q(home_team__isnull=True) | Q(away_team__isnull=True)
        ).select_related("home_team", "away_team")
    )
    if not local or not fixtures:
        return 0, []

    by_code, by_name = _team_index(competition)
    # Resolve each feed fixture's teams up front; drop any we can't fully map.
    resolved = []
    for fx in fixtures:
        home = _resolve_team(by_code, by_name, fx["home_code"], fx["home_name"])
        away = _resolve_team(by_code, by_name, fx["away_code"], fx["away_name"])
        if home and away and home.id != away.id:
            resolved.append((fx["stage"], fx["kickoff"], home, away))

    window = consts.FOOTBALL_DATA_BRACKET_WINDOW_HOURS * 3600
    # All (delta, local, feed) candidates within the same stage + window, then
    # assign greedily nearest-first with each side used at most once.
    candidates = []
    for fx_i, (stage, when, _home, _away) in enumerate(resolved):
        for lm in local:
            if lm.stage != stage:
                continue
            delta = abs((lm.kickoff - when).total_seconds())
            if delta <= window:
                candidates.append((delta, lm.pk, fx_i))
    candidates.sort()

    local_by_pk = {lm.pk: lm for lm in local}
    used_local, used_fx = set(), set()
    assigned = 0
    messages = []
    for _delta, pk, fx_i in candidates:
        if pk in used_local or fx_i in used_fx:
            continue
        lm = local_by_pk[pk]
        _stage, _when, home, away = resolved[fx_i]
        if lm.home_team_id is None and lm.away_team_id is None:
            updates, new_home, new_away = {"home_team": home, "away_team": away}, home, away
        else:
            # One side already known (admin-set or a prior partial): only fill
            # the empty slot, with whichever feed team isn't the known one.
            known = lm.home_team_id or lm.away_team_id
            missing = away if home.id == known else home
            if lm.home_team_id is None:
                updates, new_home, new_away = {"home_team": missing}, missing, lm.away_team
            else:
                updates, new_home, new_away = {"away_team": missing}, lm.home_team, missing
        Match.objects.filter(pk=pk).update(**updates)
        used_local.add(pk)
        used_fx.add(fx_i)
        assigned += 1
        messages.append((logging.INFO, consts.MSG_BRACKET_ASSIGNED.format(
            n=lm.match_number,
            home=new_home.name_fa if new_home else "?",
            away=new_away.name_fa if new_away else "?",
        )))
    return assigned, messages


# --------------------------------------------------------------------------- #
# Lazy finalization — no cron: triggered from the live endpoint when due
# --------------------------------------------------------------------------- #
def _pending_q(now):
    """Matches whose official result is overdue: the live provider says full
    time but the official status hasn't caught up, or kickoff is long enough
    past that the match must be over even if the live feed missed it — capped
    so ancient unfilled matches don't keep the sync firing forever."""
    return (
        Q(live_status=consts.LiveStatus.FULL_TIME)
        | Q(kickoff__lte=now - timedelta(hours=consts.RESULTS_PENDING_AFTER_HOURS))
    ) & Q(
        kickoff__gte=now - timedelta(hours=consts.RESULTS_PENDING_MAX_HOURS),
    ) & ~Q(status=consts.MatchStatus.FINISHED)


def _bracket_pending_q(now):
    """Knockout matches still missing a team whose kickoff is near (a few days
    out through the result-chasing cap) — so the bracket fills in as soon as the
    draw is known, without firing on matches that are weeks away or long past."""
    return (
        Q(stage__in=consts.KNOCKOUT_STAGES)
        & (Q(home_team__isnull=True) | Q(away_team__isnull=True))
        & Q(kickoff__lte=now + timedelta(hours=consts.BRACKET_LOOKAHEAD_HOURS))
        & Q(kickoff__gte=now - timedelta(hours=consts.RESULTS_PENDING_MAX_HOURS))
    )


def finalize_if_due(competition, now=None):
    """Pull official results and mirror the knockout bracket when due.

    Cheap no-op when nothing is pending (no result overdue and no knockout slot
    to fill), the token isn't configured, or the competition isn't the World Cup
    (football-data's WC feed only maps onto the real schedule). Otherwise
    atomically claims results_checked_at — losers return immediately — and the
    single winner fetches the feed once, fills any decided knockout teams, then
    applies finished results (a freshly-filled match can finalize in the same
    run). Returns True if a fetch ran.
    """
    from .models import Competition, Match

    # The source code below is football-data's World Cup feed; applying it to
    # any other competition (e.g. the test cup, which reuses real team codes)
    # could finalize wrong matches.
    if competition.slug != sd.WC2026_SLUG:
        return False
    token = (os.environ.get(consts.FOOTBALL_DATA_TOKEN_ENV) or "").strip()
    if not token:
        return False

    now = now or timezone.now()
    pending = Match.objects.filter(competition=competition)
    if not (pending.filter(_pending_q(now)).exists()
            or pending.filter(_bracket_pending_q(now)).exists()):
        return False

    cutoff = now - timedelta(seconds=consts.RESULTS_SYNC_SECONDS)
    claimed = Competition.objects.filter(pk=competition.pk).filter(
        Q(results_checked_at__isnull=True) | Q(results_checked_at__lt=cutoff)
    ).update(results_checked_at=now)
    if not claimed:
        return False

    try:
        payload = fetch_all_matches(token, consts.FOOTBALL_DATA_WC_CODE)
    except ResultsFetchError as exc:
        logger.warning("results sync: %s", exc)
        return False

    # Fill decided knockout teams first, so a match that's both freshly drawn
    # and already finished is matchable by the result pass below.
    assigned, bracket_messages = apply_bracket(competition, extract_fixtures(payload), now)
    for level, text in bracket_messages:
        logger.log(level, "bracket: %s", text)
    if assigned:
        logger.info("bracket: %s", consts.MSG_BRACKET_DONE.format(assigned=assigned))

    results = normalize(payload)
    updated, unchanged, unmatched, messages = apply_results(competition, results)
    for level, text in messages:
        logger.log(level, "results sync: %s", text)
    logger.info("results sync: %s", consts.MSG_SYNC_DONE.format(
        updated=updated, unchanged=unchanged, unmatched=unmatched, total=len(results),
    ))
    return True
