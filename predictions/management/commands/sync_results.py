"""
Pull finished match results from football-data.org and update the local schedule.

Thin CLI wrapper around predictions/results_sync.py — the same core that the
live API endpoint uses to lazily finalize results when a match ends (see
``results_sync.finalize_if_due``). Setting a match's scores triggers the
post_save signal that recomputes everyone's points (predictions/signals.py).

Design notes (implemented in results_sync.py):
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
import logging
import os

from django.core.management.base import BaseCommand, CommandError

from predictions import consts, seed_data as sd
from predictions.models import Competition
from predictions.results_sync import (
    ResultsFetchError,
    apply_results,
    fetch_matches,
    normalize,
)


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

        try:
            results = normalize(fetch_matches(token, options["source"]))
        except ResultsFetchError as exc:
            raise CommandError(str(exc))

        dry_run = options["dry_run"]
        updated, unchanged, unmatched, messages = apply_results(
            comp, results, dry_run=dry_run,
        )
        for level, text in messages:
            if level >= logging.WARNING:
                self.stdout.write(self.style.WARNING(text))
            else:
                self.stdout.write(text)

        if dry_run:
            self.stdout.write(self.style.WARNING(consts.MSG_SYNC_DRY_RUN))

        self.stdout.write(self.style.SUCCESS(consts.MSG_SYNC_DONE.format(
            updated=updated, unchanged=unchanged, unmatched=unmatched, total=len(results),
        )))
