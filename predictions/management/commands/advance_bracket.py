from django.core.management.base import BaseCommand

from predictions import bracket
from predictions.models import Competition


class Command(BaseCommand):
    help = "پرکردن خودکار تیم‌های مرحلهٔ حذفی از روی نتیجهٔ بازی‌های قبلی."

    def add_arguments(self, parser):
        parser.add_argument(
            "--competition", help="نامک تورنمنت (اختیاری) برای محدود کردن به یک مسابقه.",
        )

    def handle(self, *args, **options):
        competitions = Competition.objects.filter(is_active=True)
        if options.get("competition"):
            competitions = competitions.filter(slug=options["competition"])

        total = sum(bracket.advance_bracket(c) for c in competitions)
        self.stdout.write(self.style.SUCCESS(
            f"{total} تیم در مرحلهٔ حذفی جای‌گذاری شد."
        ))
