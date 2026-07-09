from django.core.management.base import BaseCommand
from django.utils import timezone

from predictions.models import Competition, TournamentOutcome
from predictions.scoring import settle_bonus_scores


class Command(BaseCommand):
    help = (
        "محاسبهٔ امتیاز پیش‌بینی‌های ویژه (قهرمان، آقای گل، قهرمان مسابقه و…) "
        "بر اساس نتیجهٔ نهایی ثبت‌شدهٔ تورنمنت."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--competition", help="نامک تورنمنت (اختیاری) برای محدود کردن محاسبه.",
        )

    def handle(self, *args, **options):
        competitions = Competition.objects.all()
        if options.get("competition"):
            competitions = competitions.filter(slug=options["competition"])

        now = timezone.now()
        total = 0
        for competition in competitions:
            total += settle_bonus_scores(competition)
            # Stamp the outcome (if any) so the API/UI can show it as settled.
            TournamentOutcome.objects.filter(competition=competition).update(settled_at=now)

        self.stdout.write(self.style.SUCCESS(
            f"{competitions.count()} تورنمنت پردازش شد و {total} امتیاز ویژه محاسبه شد."
        ))
