"""
Run one Telegram reminder tick (manual / local equivalent of the scheduler).

Thin CLI wrapper around ``predictions/telegram.py``'s ``run_tick`` — the same
core the secret-gated ``/api/tasks/tick/`` endpoint runs when the GitHub Actions
cron hits it in production. One tick:

- drains pending bot updates (links accounts from ``/start <token>``),
- refreshes live scores and finalizes any due official results, then
- sends due reminders (the morning digest + the pre-kickoff nudge).

Everything is env-gated: with no ``TELEGRAM_BOT_TOKEN`` configured every send and
poll is a silent no-op, so this is safe to run before the bot exists.

Usage:
    manage.py send_telegram_notifications
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from predictions import telegram


class Command(BaseCommand):
    help = (
        "اجرای یک دور یادآوری تلگرام: دریافت پیام‌های ربات، به‌روزرسانی نتایج زنده و "
        "نهایی، و ارسال یادآوری بازی‌های پیش‌بینی‌نشده."
    )

    def handle(self, *args, **options):
        result = telegram.run_tick(timezone.now())
        self.stdout.write(self.style.SUCCESS(
            "tick: polled={polled} live={live} finalized={finalized} "
            "digests={digests} nudges={nudges}".format(**result)
        ))
