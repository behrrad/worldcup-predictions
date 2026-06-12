"""
Live (in-play) scores.

Pulls the current score/minute of matches that are being played right now from
a free live provider and stores them on Match's ``live_*`` fields, which the
API exposes for display. Two hard rules keep this safe:

1. **Live data never feeds the scoring engine.** The live fields are written
   with ``queryset.update()`` so ``Match.save()`` — which treats any score as
   the final result, flips the match to FINISHED and recomputes points — never
   runs on provider data. Official results still arrive only via the admin or
   ``sync_results`` (football-data.org).

2. **Lazy fetch-on-read, one upstream request per window.** There is no cron
   or worker (free hosting): ``refresh_if_stale`` is called from the live API
   endpoint, claims ``Competition.live_checked_at`` atomically, and only the
   winner contacts the provider. However many users poll, upstream sees at
   most one request per ``consts.LIVE_REFRESH_SECONDS`` — and none at all
   outside the window in which a match could plausibly be in play.

Providers (both unofficial, both keyless, fetched defensively):

- **ESPN** (primary): one scoreboard request returns every World Cup match of
  the current scoreboard day with score, clock and a clean status machine.
  Teams carry FIFA-style codes + English names, matched like sync_results.
- **Varzesh3** (fallback): the livescore feed behind varzesh3.com. Teams carry
  Persian names only, so matching uses kickoff time + name_fa containment.

A provider response is parsed into a small normalized snapshot (one dict per
in-play/just-finished match); anything malformed is skipped, and any provider
error degrades to "no live data" rather than an exception reaching the user.
"""
import json
import logging
import urllib.error
import urllib.request
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from . import consts

logger = logging.getLogger(__name__)


class LiveFetchError(Exception):
    """A provider could not be fetched or returned an unusable payload."""


# --------------------------------------------------------------------------- #
# Fetching & parsing — provider payload -> normalized snapshot rows
# --------------------------------------------------------------------------- #
def _get_json(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": consts.LIVE_USER_AGENT}
    )
    try:
        with urllib.request.urlopen(
            request, timeout=consts.LIVE_FETCH_TIMEOUT
        ) as resp:
            raw = resp.read().decode("utf-8")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise LiveFetchError(f"{url}: {exc}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LiveFetchError(f"{url}: invalid JSON ({exc})")


def _parse_dt(value):
    """ISO datetime (provider format, 'Z' suffix) -> aware datetime, or None."""
    if not value:
        return None
    try:
        return timezone.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _clean_minute(value):
    """Provider clock ("54'", "45'+4'") -> bare "54" / "45+4", length-capped."""
    cleaned = str(value or "").replace("'", "").replace("’", "").strip()
    return cleaned[: consts.LIVE_MINUTE_MAX_LENGTH]


def _row(kickoff, status, minute, home_score, away_score, *,
         home_code=None, away_code=None, home_en=None, away_en=None,
         home_fa=None, away_fa=None):
    """One normalized snapshot entry. This is the only shape the rest of the
    module (and the matcher) ever sees, whichever provider produced it."""
    return {
        "kickoff": kickoff,
        "status": status,
        "minute": minute if status == consts.LiveStatus.LIVE else "",
        "home_score": home_score,
        "away_score": away_score,
        "home_code": home_code,
        "away_code": away_code,
        "home_en": (home_en or "").strip().lower(),
        "away_en": (away_en or "").strip().lower(),
        "home_fa": _normalize_fa(home_fa),
        "away_fa": _normalize_fa(away_fa),
    }


def fetch_espn():
    """Normalized snapshot from ESPN's World Cup scoreboard (primary)."""
    payload = _get_json(consts.ESPN_SCOREBOARD_URL)
    if not isinstance(payload, dict):
        raise LiveFetchError("espn: unexpected payload shape")

    rows = []
    for event in payload.get("events") or []:
        try:
            competition = event["competitions"][0]
            status_type = competition["status"]["type"]
            state = status_type.get("state")
            if state == consts.ESPN_STATE_PRE:
                continue
            if state == consts.ESPN_STATE_IN:
                status = (
                    consts.LiveStatus.HALFTIME
                    if status_type.get("name") == consts.ESPN_STATUS_HALFTIME
                    else consts.LiveStatus.LIVE
                )
            elif state == consts.ESPN_STATE_POST:
                status = consts.LiveStatus.FULL_TIME
            else:
                continue

            sides = {}
            for competitor in competition["competitors"]:
                sides[competitor.get("homeAway")] = competitor
            home, away = sides[consts.ESPN_HOME], sides[consts.ESPN_AWAY]

            kickoff = _parse_dt(event.get("date"))
            if kickoff is None:
                continue
            rows.append(_row(
                kickoff, status,
                _clean_minute(competition["status"].get("displayClock")),
                int(home["score"]), int(away["score"]),
                home_code=home["team"].get("abbreviation"),
                away_code=away["team"].get("abbreviation"),
                home_en=home["team"].get("displayName"),
                away_en=away["team"].get("displayName"),
            ))
        except (KeyError, IndexError, TypeError, ValueError):
            # One malformed event never poisons the rest of the snapshot.
            continue
    return rows


def fetch_varzesh3():
    """Normalized snapshot from Varzesh3's livescore feed (fallback).

    The feed mixes sports (football is sport == 1) and identifies teams by
    Persian name only — no codes, no English names."""
    payload = _get_json(consts.VARZESH3_LIVESCORE_URL)
    if not isinstance(payload, list):
        raise LiveFetchError("varzesh3: unexpected payload shape")

    rows = []
    for league in payload:
        if not isinstance(league, dict):
            continue
        if league.get("sport") != consts.VARZESH3_SPORT_FOOTBALL:
            continue
        for group in league.get("dates") or []:
            for match in (group or {}).get("matches") or []:
                try:
                    status_code = match.get("status")
                    if status_code == consts.Varzesh3Status.LIVE:
                        status = (
                            consts.LiveStatus.HALFTIME
                            if match.get("statusTitle") == consts.VARZESH3_HALFTIME_TITLE
                            else consts.LiveStatus.LIVE
                        )
                    elif status_code == consts.Varzesh3Status.FINISHED:
                        status = consts.LiveStatus.FULL_TIME
                    else:
                        continue

                    goals = match["goals"]
                    kickoff = _parse_dt(match.get("startOnUtc"))
                    if kickoff is None:
                        continue
                    rows.append(_row(
                        kickoff, status, _clean_minute(match.get("liveTime")),
                        int(goals["host"]), int(goals["guest"]),
                        home_fa=match["host"]["name"],
                        away_fa=match["guest"]["name"],
                    ))
                except (KeyError, TypeError, ValueError):
                    continue
    return rows


# --------------------------------------------------------------------------- #
# Matching — snapshot rows -> local Match objects
# --------------------------------------------------------------------------- #
def _normalize_fa(name):
    """Normalize a Persian team name for comparison (ZWNJ/whitespace noise)."""
    if not name:
        return ""
    return " ".join(str(name).replace("‌", " ").split())


def _fa_matches(provider_name, local_name):
    """Provider spellings are often shorter («بوسنی» for «بوسنی و هرزگوین»),
    so accept containment either way, never just a prefix of one word."""
    if not provider_name or not local_name:
        return False
    return provider_name == local_name or provider_name in local_name or local_name in provider_name


def _within_window(match, row):
    return (
        abs((match.kickoff - row["kickoff"]).total_seconds())
        <= consts.LIVE_MATCH_WINDOW_HOURS * 3600
    )


def _find_match(row, matches):
    """Locate the local match a snapshot row refers to.

    Returns (match, swapped) where swapped=True means the provider's home side
    is our away side (scores must be flipped). Identification order:
      1. team-code pair (ESPN),
      2. English-name pair (ESPN fallback),
      3. Persian-name containment (Varzesh3) — disambiguated by kickoff, which
         also guards all strategies against same-pairing rematches.
    """
    def by_pair(getter):
        direct, swapped = [], []
        for m in matches:
            if not _within_window(m, row):
                continue
            home_key, away_key = getter(m)
            if not home_key or not away_key:
                continue
            if (home_key, away_key) == (row_home, row_away):
                direct.append(m)
            elif (home_key, away_key) == (row_away, row_home):
                swapped.append(m)
        if direct:
            return direct, False
        return swapped, True

    strategies = []
    if row["home_code"] and row["away_code"]:
        row_home, row_away = row["home_code"], row["away_code"]
        strategies.append(by_pair(lambda m: (m.home_team.code, m.away_team.code)))
    if row["home_en"] and row["away_en"]:
        row_home, row_away = row["home_en"], row["away_en"]
        strategies.append(by_pair(
            lambda m: (m.home_team.name_en.strip().lower(),
                       m.away_team.name_en.strip().lower())
        ))

    for candidates, swapped in strategies:
        if candidates:
            best = min(
                candidates,
                key=lambda m: abs((m.kickoff - row["kickoff"]).total_seconds()),
            )
            return best, swapped

    # Persian containment (Varzesh3): try direct orientation, then swapped.
    if row["home_fa"] and row["away_fa"]:
        for provider_home, provider_away, swapped in (
            (row["home_fa"], row["away_fa"], False),
            (row["away_fa"], row["home_fa"], True),
        ):
            candidates = [
                m for m in matches
                if _within_window(m, row)
                and _fa_matches(provider_home, _normalize_fa(m.home_team.name_fa))
                and _fa_matches(provider_away, _normalize_fa(m.away_team.name_fa))
            ]
            if candidates:
                best = min(
                    candidates,
                    key=lambda m: abs((m.kickoff - row["kickoff"]).total_seconds()),
                )
                return best, swapped

    return None, False


def apply_snapshot(competition, rows, now=None):
    """Write a normalized snapshot onto the competition's matches.

    Only the live_* fields are touched, always via queryset.update() (never
    save(), which would finalize results / trigger scoring). Matches that have
    an official result are ignored entirely. Live state that the provider no
    longer reports is cleared once it is stale, so a dead feed can't leave a
    «زنده» badge stuck on the page. Returns the number of matches updated.
    """
    from .models import Match

    now = now or timezone.now()
    matches = [
        m for m in Match.objects.filter(competition=competition)
        .select_related("home_team", "away_team")
        if m.home_team_id and m.away_team_id and not m.is_finished
    ]

    written = 0
    matched_ids = set()
    for row in rows:
        match, swapped = _find_match(row, matches)
        if match is None or match.id in matched_ids:
            continue
        matched_ids.add(match.id)
        home_score, away_score = (
            (row["away_score"], row["home_score"]) if swapped
            else (row["home_score"], row["away_score"])
        )
        changed = (
            match.live_status != row["status"]
            or match.live_minute != row["minute"]
            or match.live_home_score != home_score
            or match.live_away_score != away_score
        )
        if not changed:
            continue
        Match.objects.filter(pk=match.pk).update(
            live_home_score=home_score,
            live_away_score=away_score,
            live_minute=row["minute"],
            live_status=row["status"],
            live_updated_at=now,
        )
        written += 1

    # Clear live state the provider stopped reporting: finished entries vanish
    # on the provider's day rollover and are cleared right away; an in-play
    # entry is only cleared once stale, so one flaky partial response can't
    # blank an ongoing match.
    stale_before = now - timedelta(seconds=consts.LIVE_STALE_CLEAR_SECONDS)
    Match.objects.filter(competition=competition).exclude(
        live_status=consts.LiveStatus.NONE
    ).exclude(pk__in=matched_ids).filter(
        Q(live_status=consts.LiveStatus.FULL_TIME)
        | Q(live_updated_at__isnull=True)
        | Q(live_updated_at__lt=stale_before)
    ).update(
        live_home_score=None,
        live_away_score=None,
        live_minute="",
        live_status=consts.LiveStatus.NONE,
        live_updated_at=now,
    )
    return written


# --------------------------------------------------------------------------- #
# Refresh gate — at most one upstream fetch per window, no cron required
# --------------------------------------------------------------------------- #
def _live_window_q(now):
    """Matches that could plausibly be in play right now: kickoff in the recent
    past (or imminent), or already carrying in-play live state (covers extra
    time/penalties beyond the nominal window, and lets stale state get cleaned
    up after the provider drops a match)."""
    return (
        Q(
            status=consts.MatchStatus.SCHEDULED,
            kickoff__gte=now - timedelta(hours=consts.LIVE_WINDOW_BEFORE_HOURS),
            kickoff__lte=now + timedelta(minutes=consts.LIVE_WINDOW_AFTER_MINUTES),
        )
        | Q(live_status__in=(consts.LiveStatus.LIVE, consts.LiveStatus.HALFTIME))
    )


def refresh_if_stale(competition, now=None):
    """Refresh the competition's live scores if the snapshot is stale.

    Cheap no-op when no match can be live. Otherwise atomically claims the
    competition's live_checked_at stamp — losers return immediately and serve
    whatever is in the DB — and the single winner fetches the primary
    provider, falling back to the secondary. Returns True if a fetch ran.
    """
    from .models import Competition, Match

    now = now or timezone.now()
    if not Match.objects.filter(
        competition=competition
    ).filter(_live_window_q(now)).exists():
        return False

    cutoff = now - timedelta(seconds=consts.LIVE_REFRESH_SECONDS)
    claimed = Competition.objects.filter(pk=competition.pk).filter(
        Q(live_checked_at__isnull=True) | Q(live_checked_at__lt=cutoff)
    ).update(live_checked_at=now)
    if not claimed:
        return False

    # Primary first; the fallback runs only if the primary fails. Resolved at
    # call time (not a module constant) so tests can patch the fetchers.
    providers = (
        (consts.LIVE_PROVIDER_ESPN, fetch_espn),
        (consts.LIVE_PROVIDER_VARZESH3, fetch_varzesh3),
    )
    for name, fetcher in providers:
        try:
            rows = fetcher()
        except LiveFetchError as exc:
            logger.warning("live scores: %s failed: %s", name, exc)
            continue
        apply_snapshot(competition, rows, now)
        return True

    logger.error("live scores: all providers failed")
    return False
