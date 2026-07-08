"""
Broadcast the 2× knockout-boost announcement to every reachable member on
Telegram (linked bot + reminders opt-in).

One-off, manual, and idempotent: each member is messaged at most once for this
campaign (guarded by a NotificationLog row keyed on consts.ANNOUNCE_2X_CAMPAIGN),
so re-running only reaches members who haven't been notified yet. With no bot
configured every send is a silent no-op.

Usage:
    manage.py broadcast_telegram            # send for real
    manage.py broadcast_telegram --dry-run  # list recipients, send nothing
"""
from django.core.management.base import BaseCommand

from predictions import consts, telegram


class Command(BaseCommand):
    help = "ارسال اطلاعیهٔ ۲برابرشدن ضریب مراحل حذفی به اعضای متصل به تلگرام."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="فقط فهرست گیرندگان را نشان بده و چیزی نفرست.",
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            recipients = list(telegram._linked_users("telegram_notify"))
            self.stdout.write(
                f"[dry-run] configured={telegram.is_configured()} "
                f"recipients={len(recipients)}"
            )
            for user in recipients:
                self.stdout.write(f"  - {user.public_name} (chat {user.telegram_chat_id})")
            return

        sent = telegram.broadcast_announcement(
            telegram.announcement_2x_message(), consts.ANNOUNCE_2X_CAMPAIGN,
        )
        self.stdout.write(self.style.SUCCESS(f"announcement sent to {sent} member(s)"))
