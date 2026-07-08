from django.core.management.base import BaseCommand

from predictions import seed_data
from predictions.models import Competition, PlayerCandidate, Team


class Command(BaseCommand):
    help = (
        "افزودن فهرست اولیهٔ بازیکنان نامزد جوایز فردی (آقای گل / بهترین بازیکن) "
        "به جام جهانی ۲۰۲۶. تکراری‌ها به‌روزرسانی می‌شوند."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--competition", default=seed_data.WC2026_SLUG,
            help="نامک تورنمنت (پیش‌فرض: جام جهانی ۲۰۲۶).",
        )

    def handle(self, *args, **options):
        slug = options["competition"]
        try:
            competition = Competition.objects.get(slug=slug)
        except Competition.DoesNotExist:
            self.stderr.write(self.style.ERROR(
                f"تورنمنت «{slug}» پیدا نشد؛ ابتدا seed_worldcup2026 را اجرا کنید."
            ))
            return

        # Team lookup by code, once, so a missing code just leaves the link blank.
        teams = {t.code: t for t in Team.objects.filter(competition=competition) if t.code}
        created = updated = 0
        for name, code in seed_data.WC2026_PLAYER_CANDIDATES:
            _obj, was_created = PlayerCandidate.objects.update_or_create(
                competition=competition, name=name,
                defaults={"team": teams.get(code)},
            )
            created += was_created
            updated += not was_created

        self.stdout.write(self.style.SUCCESS(
            f"{created} بازیکن اضافه و {updated} بازیکن به‌روزرسانی شد "
            f"(از {len(seed_data.WC2026_PLAYER_CANDIDATES)} نامزد)."
        ))
