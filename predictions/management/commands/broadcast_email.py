"""
Email the 2× knockout-boost announcement to every league member with a real
email address.

Env-gated on RESEND_API_KEY: with no key configured this is a silent no-op (the
feature ships dark), so it's safe to run before email is wired up — use
``--dry-run`` to preview the recipient list. Idempotent: each member is emailed
at most once for this campaign (NotificationLog guard on
consts.ANNOUNCE_2X_EMAIL_CAMPAIGN), so re-running only reaches the not-yet-mailed.

Usage:
    manage.py broadcast_email            # send for real (needs RESEND_API_KEY)
    manage.py broadcast_email --dry-run  # list recipients, send nothing
"""
from django.core.management.base import BaseCommand

from predictions import consts, email


class Command(BaseCommand):
    help = "ارسال اطلاعیهٔ ۲برابرشدن ضریب مراحل حذفی از طریق ایمیل به اعضا."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="فقط فهرست گیرندگان را نشان بده و چیزی نفرست.",
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            recipients = email.announcement_recipients()
            self.stdout.write(
                f"[dry-run] configured={email.is_configured()} "
                f"recipients={len(recipients)}"
            )
            for user in recipients:
                self.stdout.write(f"  - {user.public_name} <{user.email}>")
            return

        sent = email.broadcast_announcement(
            consts.EMAIL_ANNOUNCE_2X_SUBJECT,
            consts.EMAIL_ANNOUNCE_2X_BODY,
            consts.ANNOUNCE_2X_EMAIL_CAMPAIGN,
        )
        self.stdout.write(self.style.SUCCESS(f"announcement emailed to {sent} member(s)"))
