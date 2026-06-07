from django.core.management.base import BaseCommand

from predictions import consts
from predictions.models import Match
from predictions.scoring import recompute_match_scores


class Command(BaseCommand):
    help = "محاسبهٔ دوبارهٔ امتیاز همهٔ بازی‌های پایان‌یافته در تمام مسابقه‌ها."

    def add_arguments(self, parser):
        parser.add_argument(
            "--competition", help="نامک تورنمنت (اختیاری) برای محدود کردن محاسبه.",
        )

    def handle(self, *args, **options):
        matches = Match.objects.filter(status=consts.MatchStatus.FINISHED)
        if options.get("competition"):
            matches = matches.filter(competition__slug=options["competition"])

        total = sum(recompute_match_scores(match) for match in matches)
        self.stdout.write(self.style.SUCCESS(
            f"{matches.count()} بازی پردازش شد و {total} امتیاز محاسبه شد."
        ))
