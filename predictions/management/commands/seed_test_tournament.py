import datetime

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from predictions import seed_data as sd
from predictions.models import Competition, Match, Team


class Command(BaseCommand):
    help = (
        "ساخت «جام آزمایشی» با تایم‌لاین فشرده (نسبت به همین لحظه) برای آزمایش منطق‌ها: "
        "بازی‌های باز، بسته‌شده و پایان‌یافته. هر بار اجرا، زمان‌بندی را تازه می‌کند."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()
        comp, _ = Competition.objects.get_or_create(
            slug=sd.TEST_CUP_SLUG,
            defaults={"name": sd.TEST_CUP_NAME, "start_date": now.date(),
                      "is_active": True},
        )
        teams = []
        for name_fa, code, flag in sd.TEST_CUP_TEAMS:
            team, _ = Team.objects.get_or_create(
                competition=comp, name_fa=name_fa,
                defaults={"code": code, "flag_emoji": flag, "group": "T"},
            )
            teams.append(team)

        # Refresh the timeline by UPSERTING each match by its number, so existing
        # predictions/scores (and stable match ids) are preserved across reruns.
        open_n = locked_n = finished_n = 0
        for i, (h, a, mins, hs, as_, stage) in enumerate(sd.TEST_CUP_SCHEDULE, start=1):
            match, _ = Match.objects.update_or_create(
                competition=comp, match_number=i,
                defaults={
                    "stage": stage,
                    "home_team": teams[h],
                    "away_team": teams[a],
                    "kickoff": now + datetime.timedelta(minutes=mins),
                    "home_score": hs,
                    "away_score": as_,
                },
            )
            if match.is_finished:
                finished_n += 1
            elif match.is_open_for(sd.DEMO_LOCK_MINUTES, now=now):
                open_n += 1
            else:
                locked_n += 1

        self.stdout.write(self.style.SUCCESS(
            f"«{comp.name}» آماده شد: {len(teams)} تیم، "
            f"{open_n} بازی باز، {locked_n} بازی بسته و {finished_n} بازی پایان‌یافته."
        ))
