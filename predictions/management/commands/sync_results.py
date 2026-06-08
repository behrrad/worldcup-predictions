"""
Pull finished match results from football-data.org and update the local schedule.

Setting a match's scores triggers the post_save signal that recomputes everyone's
points (see predictions/signals.py), so a sync run keeps every league's
leaderboard current with no manual data entry.

Design notes:
- Only **FINISHED** matches with a full-time score are touched — in-play scores
  are ignored so a match isn't marked finished (and locked) prematurely.
- Results are matched to local matches by the two team codes (football-data's
  `tla`), with an English-name fallback for code mismatches, and disambiguated
  by nearest kickoff when a pairing recurs. Unmatched results are logged, never
  guessed at.
- Re-running is idempotent: a result already stored is reported as "unchanged".
- Knockout matches whose teams aren't decided yet simply don't match anything
  (filling those in is the separate auto-progress concern).

Usage:
    manage.py sync_results [--token TOKEN] [--competition SLUG] [--dry-run]

The API token comes from --token or the FOOTBALL_DATA_API_TOKEN env var.
"""
import json
import os
import urllib.error
import urllib.request
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from predictions import consts, seed_data as sd
from predictions.models import Competition, Match


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
        raise CommandError(consts.MSG_SYNC_HTTP_ERROR.format(error=exc))
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise CommandError(consts.MSG_SYNC_BAD_JSON)


def _normalize(payload):
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


def _pick(candidates, utc_date):
    """From matches sharing a team pairing, pick the one closest to utc_date."""
    when = _parse_dt(utc_date)
    if len(candidates) == 1 or when is None:
        return candidates[0]
    return min(candidates, key=lambda m: abs((m.kickoff - when).total_seconds()))


class Command(BaseCommand):
    help = (
        "دریافت نتایج بازی‌های پایان‌یافته از football-data.org و به‌روزرسانی برنامهٔ "
        "محلی (امتیازها به‌صورت خودکار دوباره محاسبه می‌شوند)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--token", default=os.environ.get(consts.FOOTBALL_DATA_TOKEN_ENV, ""),
            help="توکن دسترسی football-data.org (پیش‌فرض از متغیر محیطی).",
        )
        parser.add_argument(
            "--competition", default=sd.WC2026_SLUG,
            help="نامک تورنمنت محلی (پیش‌فرض: جام جهانی ۲۰۲۶).",
        )
        parser.add_argument(
            "--source", default=consts.FOOTBALL_DATA_WC_CODE,
            help="کد تورنمنت در football-data (پیش‌فرض: WC).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="فقط گزارش بده؛ چیزی ذخیره نکن.",
        )

    def handle(self, *args, **options):
        token = (options["token"] or "").strip()
        if not token:
            raise CommandError(consts.MSG_SYNC_NO_TOKEN)
        try:
            comp = Competition.objects.get(slug=options["competition"])
        except Competition.DoesNotExist:
            raise CommandError(
                consts.MSG_SYNC_NO_COMPETITION.format(slug=options["competition"])
            )

        results = _normalize(fetch_matches(token, options["source"]))

        # Index local matches that have both teams, by code pairing and by
        # English-name pairing (the fallback for code mismatches).
        by_code, by_name = {}, {}
        for m in comp.matches.select_related("home_team", "away_team"):
            if m.home_team_id and m.away_team_id:
                by_code.setdefault((m.home_team.code, m.away_team.code), []).append(m)
                key = (m.home_team.name_en.strip().lower(),
                       m.away_team.name_en.strip().lower())
                by_name.setdefault(key, []).append(m)

        dry_run = options["dry_run"]
        updated = unchanged = unmatched = 0

        with transaction.atomic():
            for r in results:
                candidates = (
                    by_code.get((r["home_code"], r["away_code"]))
                    or by_name.get((r["home_name"], r["away_name"]))
                )
                if not candidates:
                    unmatched += 1
                    self.stdout.write(self.style.WARNING(consts.MSG_SYNC_UNMATCHED.format(
                        home=r["home_code"] or r["home_name"],
                        away=r["away_code"] or r["away_name"],
                        date=r["utc_date"],
                    )))
                    continue

                match = _pick(candidates, r["utc_date"])
                if (match.home_score == r["home_score"]
                        and match.away_score == r["away_score"]):
                    unchanged += 1
                    continue

                updated += 1
                self.stdout.write(consts.MSG_SYNC_UPDATED.format(
                    n=match.match_number, home=match.home_team.name_fa,
                    hs=r["home_score"], as_=r["away_score"], away=match.away_team.name_fa,
                ))
                if not dry_run:
                    match.home_score = r["home_score"]
                    match.away_score = r["away_score"]
                    match.save()  # post_save signal recomputes scores

            if dry_run:
                self.stdout.write(self.style.WARNING(consts.MSG_SYNC_DRY_RUN))
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(consts.MSG_SYNC_DONE.format(
            updated=updated, unchanged=unchanged, unmatched=unmatched, total=len(results),
        )))
