import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from predictions import consts, seed_data as sd
from predictions.models import Competition, Match, Team


class Command(BaseCommand):
    help = "ساخت تورنمنت جام جهانی ۲۰۲۶ همراه با تیم‌ها، بازی‌های گروهی و جدول مراحل حذفی."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true",
            help="حذف تیم‌ها و بازی‌های قبلی این تورنمنت و ساخت دوباره.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        tz = ZoneInfo(settings.TIME_ZONE)
        year, month, day = sd.WC2026_START
        start_date = datetime.date(year, month, day)
        base = datetime.datetime(year, month, day, 18, 0, tzinfo=tz)

        comp, _ = Competition.objects.get_or_create(
            slug=sd.WC2026_SLUG,
            defaults={"name": sd.WC2026_NAME, "start_date": start_date, "is_active": True},
        )

        if options["reset"]:
            comp.matches.all().delete()
            comp.teams.all().delete()
            self.stdout.write(self.style.WARNING("داده‌های قبلی این تورنمنت پاک شد."))

        if comp.matches.exists():
            self.stdout.write(self.style.WARNING(
                "این تورنمنت از قبل بازی دارد. برای ساخت دوباره از --reset استفاده کنید."
            ))
            return

        # --- Teams --------------------------------------------------------- #
        teams = {}  # (group, index_within_group) -> Team
        for group, rows in sd.WC2026_GROUPS.items():
            for index, (name_fa, name_en, code, flag) in enumerate(rows):
                team, _ = Team.objects.get_or_create(
                    competition=comp, name_fa=name_fa,
                    defaults={"name_en": name_en, "code": code,
                              "flag_emoji": flag, "group": group},
                )
                teams[(group, index)] = team

        # --- Group-stage matches (single round-robin per group) ------------ #
        match_no = 1
        slot = 0  # one per match; used to spread kickoff times across days
        for matchday in sd.GROUP_MATCHDAYS:
            for group in sd.WC2026_GROUPS:
                for home_idx, away_idx in matchday:
                    kickoff = base + datetime.timedelta(
                        days=slot // 4, hours=(slot % 4) * 3
                    )
                    Match.objects.create(
                        competition=comp, match_number=match_no,
                        stage=consts.Stage.GROUP,
                        home_team=teams[(group, home_idx)],
                        away_team=teams[(group, away_idx)],
                        kickoff=kickoff,
                    )
                    match_no += 1
                    slot += 1

        group_matches = match_no - 1

        # --- Knockout placeholders (teams filled in later by the admin) ---- #
        knockout_start_day = (slot // 4) + 2
        for round_index, (stage, count) in enumerate(sd.KNOCKOUT_ROUNDS):
            for n in range(count):
                kickoff = base + datetime.timedelta(
                    days=knockout_start_day + round_index * 2, hours=(n % 4) * 3
                )
                Match.objects.create(
                    competition=comp, match_number=match_no, stage=stage,
                    home_team=None, away_team=None, kickoff=kickoff,
                )
                match_no += 1

        knockout_matches = (match_no - 1) - group_matches
        self.stdout.write(self.style.SUCCESS(
            f"«{comp.name}» ساخته شد: {comp.teams.count()} تیم، "
            f"{group_matches} بازی گروهی و {knockout_matches} بازی مرحلهٔ حذفی."
        ))
