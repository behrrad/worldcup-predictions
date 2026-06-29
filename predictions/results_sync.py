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


def fetch_matches(token, source_code):
    """Fetch FINISHED matches for a competition from football-data.org (v4)."""
    url = (
        f"{consts.FOOTBALL_DATA_BASE_URL}/competitions/{source_code}/matches"
        f"?status={consts.FOOTBALL_DATA_FINISHED}"
    )
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


def _strip_shootout(home, away, score):
    """The 120' scoreline for a penalty-shootout final.

    The source's fullTime *includes* the shootout goals, so subtract them back
    out (fullTime − penalties) to recover the level scoreline we score against.
    Fall back to regularTime, then to the fullTime as-is, if the shootout split
    isn't present."""
    penalties = score.get("penalties") or {}
    ph, pa = penalties.get("home"), penalties.get("away")
    if ph is not None and pa is not None:
        return home - ph, away - pa
    regular = score.get("regularTime") or {}
    if regular.get("home") is not None and regular.get("away") is not None:
        return regular["home"], regular["away"]
    return home, away


def _shootout_winner(score):
    """HOME/AWAY from the source's shootout winner enum, or '' if unknown."""
    winner = score.get("winner")
    if winner == consts.FOOTBALL_DATA_WINNER_HOME:
        return consts.Advancer.HOME
    if winner == consts.FOOTBALL_DATA_WINNER_AWAY:
        return consts.Advancer.AWAY
    return consts.Advancer.NONE


def normalize(payload):
    """Flatten the API payload to the fields we need, keeping only scored finals.

    For a penalty-shootout final the 120' result is the level scoreline (the
    source's fullTime carries the shootout goals on top), so we strip those back
    out and record which side advanced — see _strip_shootout / _shootout_winner.
    """
    results = []
    for m in payload.get("matches", []):
        if m.get("status") != consts.FOOTBALL_DATA_FINISHED:
            continue
        score = m.get("score") or {}
        full_time = score.get("fullTime") or {}
        home, away = m.get("homeTeam") or {}, m.get("awayTeam") or {}
        hs, as_ = full_time.get("home"), full_time.get("away")
        if hs is None or as_ is None:
            continue
        penalty_winner = consts.Advancer.NONE
        if score.get("duration") == consts.FOOTBALL_DATA_PENALTY:
            hs, as_ = _strip_shootout(hs, as_, score)
            penalty_winner = _shootout_winner(score)
        results.append({
            "home_code": home.get("tla"),
            "away_code": away.get("tla"),
            "home_name": (home.get("name") or "").strip().lower(),
            "away_name": (away.get("name") or "").strip().lower(),
            "home_score": hs,
            "away_score": as_,
            "penalty_winner": penalty_winner,
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
                    and match.away_score == r["away_score"]
                    and match.penalty_winner == r["penalty_winner"]):
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
                match.penalty_winner = r["penalty_winner"]
                match.save()  # post_save signal recomputes scores

        if dry_run:
            transaction.set_rollback(True)

    return updated, unchanged, unmatched, messages


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


def finalize_if_due(competition, now=None):
    """Pull official results when a match looks over but isn't finalized yet.

    Cheap no-op when nothing is pending, the token isn't configured, or the
    competition isn't the World Cup (football-data's WC feed only maps onto
    the real schedule). Otherwise atomically claims results_checked_at —
    losers return immediately — and the single winner fetches and applies.
    Returns True if a fetch ran.
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
    if not Match.objects.filter(competition=competition).filter(_pending_q(now)).exists():
        return False

    cutoff = now - timedelta(seconds=consts.RESULTS_SYNC_SECONDS)
    claimed = Competition.objects.filter(pk=competition.pk).filter(
        Q(results_checked_at__isnull=True) | Q(results_checked_at__lt=cutoff)
    ).update(results_checked_at=now)
    if not claimed:
        return False

    try:
        results = normalize(fetch_matches(token, consts.FOOTBALL_DATA_WC_CODE))
    except ResultsFetchError as exc:
        logger.warning("results sync: %s", exc)
        return False
    updated, unchanged, unmatched, messages = apply_results(competition, results)
    for level, text in messages:
        logger.log(level, "results sync: %s", text)
    logger.info("results sync: %s", consts.MSG_SYNC_DONE.format(
        updated=updated, unchanged=unchanged, unmatched=unmatched, total=len(results),
    ))
    return True
