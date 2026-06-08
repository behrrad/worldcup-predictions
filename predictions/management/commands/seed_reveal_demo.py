import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from predictions import scoring
from predictions import seed_data as sd
from predictions.models import (
    Competition,
    League,
    Match,
    Membership,
    Prediction,
    Team,
)
from predictions import consts

User = get_user_model()


class Command(BaseCommand):
    help = (
        "ساخت «دموی نمایش پیش‌بینی»: یک لیگ کامل با مدیر، چند عضو و پیش‌بینی‌هایشان، "
        "همراه با بازی‌هایی در هر چهار حالت (باز، بسته، شروع‌شده، پایان‌یافته) — برای "
        "آزمایش کلید «نمایش پیش‌بینی دیگران» و قفل ۳۰ دقیقه‌ای. هر اجرا زمان‌بندی را تازه می‌کند."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner-email",
            default=sd.REVEAL_DEMO_OWNER_EMAIL,
            help="ایمیل حساب مدیرِ لیگ دمو (پیش‌فرض: حساب اصلی برای آزمایش در اپ).",
        )

    def _get_or_make_user(self, email, display_name=""):
        user = User.objects.filter(email=email).first()
        if user:
            return user
        # Demo bots: a real (hashed) password they never use; they exist only so
        # their predictions can be shown when reveal is on.
        return User.objects.create_user(
            email=email, password="demo-pass-unused", display_name=display_name
        )

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()

        comp, _ = Competition.objects.get_or_create(
            slug=sd.REVEAL_DEMO_COMP_SLUG,
            defaults={"name": sd.REVEAL_DEMO_COMP_NAME,
                      "start_date": now.date(), "is_active": True},
        )

        teams = []
        for name_fa, code, flag in sd.TEST_CUP_TEAMS:
            team, _ = Team.objects.get_or_create(
                competition=comp, name_fa=name_fa,
                defaults={"code": code, "flag_emoji": flag, "group": "D"},
            )
            teams.append(team)

        # Owner + league (reveal left at its existing value on rerun, so a manual
        # toggle in the app survives re-seeding).
        owner = self._get_or_make_user(options["owner_email"], display_name="Behrad")
        league, _ = League.objects.get_or_create(
            competition=comp, owner=owner, name=sd.REVEAL_DEMO_LEAGUE_NAME,
        )
        Membership.objects.get_or_create(
            league=league, user=owner, defaults={"role": consts.Role.OWNER}
        )

        # Bot members, keyed by email so their predictions can be attached below.
        members_by_label = {"owner": owner}
        for email, display_name in sd.REVEAL_DEMO_MEMBERS:
            member = self._get_or_make_user(email, display_name=display_name)
            Membership.objects.get_or_create(
                league=league, user=member, defaults={"role": consts.Role.MEMBER}
            )
            members_by_label[email] = member

        # Upsert the four matches by number, refreshing kickoff/result each run.
        matches = []
        for i, (h, a, mins, hs, as_, stage) in enumerate(sd.REVEAL_DEMO_SCHEDULE, start=1):
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
            matches.append(match)

        # Predictions: every member predicts every match (so reveal has content).
        for label, picks in sd.REVEAL_DEMO_PREDICTIONS.items():
            membership = Membership.objects.get(
                league=league, user=members_by_label[label]
            )
            for match, (ph, pa) in zip(matches, picks):
                Prediction.objects.update_or_create(
                    membership=membership, match=match,
                    defaults={"predicted_home": ph, "predicted_away": pa},
                )

        # Now that predictions exist, recompute scores for finished matches.
        for match in matches:
            if match.is_finished:
                scoring.recompute_match_scores(match)

        league.refresh_from_db()
        self._report(league, matches, now)

    # -- reporting --------------------------------------------------------- #
    def _state(self, match, now):
        if match.is_finished:
            return f"پایان‌یافته {match.home_score}-{match.away_score}"
        if match.is_open_for(30, now=now):
            return "باز (پیش‌بینی مجاز)"
        if match.kickoff <= now:
            return "شروع‌شده (قفل)"
        return "بسته — داخل پنجرهٔ ۳۰ دقیقه (قفل)"

    def _report(self, league, matches, now):
        s = self.style
        self.stdout.write(s.SUCCESS(f"«{league.name}» آماده شد."))
        self.stdout.write(
            f"  مدیر: {league.owner.email}  ·  اعضا: {league.memberships.count()}  ·  "
            f"نمایش پیش‌بینی دیگران: {'روشن' if league.reveal_predictions else 'خاموش'}"
        )
        self.stdout.write(f"  آدرس لیگ در اپ:  /l/{league.slug}")
        for m in matches:
            self.stdout.write(
                f"   - بازی {m.match_number}: {m.home_team.name_fa} - {m.away_team.name_fa}"
                f"  →  {self._state(m, now)}"
            )
