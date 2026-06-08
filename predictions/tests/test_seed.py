from django.core.management import call_command
from django.test import TestCase

from predictions import consts, seed_data as sd
from predictions.models import Competition, Match, Team


class SeedCommandTests(TestCase):
    def test_seed_creates_expected_counts(self):
        call_command("seed_worldcup2026", verbosity=0)
        comp = Competition.objects.get(slug=sd.WC2026_SLUG)
        # 12 groups × 4 teams = 48
        self.assertEqual(Team.objects.filter(competition=comp).count(), 48)
        # 12 groups × 6 round-robin matches = 72 group matches
        group = Match.objects.filter(competition=comp, stage=consts.Stage.GROUP)
        self.assertEqual(group.count(), 72)
        # knockout placeholders: 16+8+4+2+1+1 = 32
        knockout = Match.objects.filter(competition=comp).exclude(stage=consts.Stage.GROUP)
        self.assertEqual(knockout.count(), 32)

    def test_seed_is_idempotent(self):
        call_command("seed_worldcup2026", verbosity=0)
        call_command("seed_worldcup2026", verbosity=0)  # second run is a no-op
        comp = Competition.objects.get(slug=sd.WC2026_SLUG)
        self.assertEqual(Team.objects.filter(competition=comp).count(), 48)
        self.assertEqual(Match.objects.filter(competition=comp).count(), 104)

    def test_iran_is_seeded(self):
        call_command("seed_worldcup2026", verbosity=0)
        self.assertTrue(Team.objects.filter(name_fa="ایران").exists())


class TestTournamentCommandTests(TestCase):
    def test_creates_compressed_timeline(self):
        from django.utils import timezone

        call_command("seed_test_tournament", verbosity=0)
        comp = Competition.objects.get(slug=sd.TEST_CUP_SLUG)
        self.assertEqual(comp.teams.count(), len(sd.TEST_CUP_TEAMS))
        self.assertEqual(comp.matches.count(), len(sd.TEST_CUP_SCHEDULE))

        now = timezone.now()
        states = [(m.is_finished, m.is_open_for(30, now)) for m in comp.matches.all()]
        self.assertEqual(sum(1 for f, _ in states if f), 3)          # 3 finished
        self.assertTrue(any(not f and o for f, o in states))         # at least one open
        self.assertTrue(any(not f and not o for f, o in states))     # at least one locked

    def test_rerun_refreshes_timeline(self):
        call_command("seed_test_tournament", verbosity=0)
        call_command("seed_test_tournament", verbosity=0)  # idempotent (re-seeds)
        comp = Competition.objects.get(slug=sd.TEST_CUP_SLUG)
        self.assertEqual(comp.matches.count(), len(sd.TEST_CUP_SCHEDULE))

    def test_rerun_preserves_predictions(self):
        from accounts.models import User
        from predictions.models import League, Membership, Prediction

        call_command("seed_test_tournament", verbosity=0)
        comp = Competition.objects.get(slug=sd.TEST_CUP_SLUG)
        user = User.objects.create_user(email="t@test.com", password="pw")
        league = League.objects.create(name="L", competition=comp, owner=user)
        mem = Membership.objects.create(league=league, user=user, role=consts.Role.OWNER)
        match = comp.matches.order_by("match_number").first()
        Prediction.objects.create(membership=mem, match=match,
                                  predicted_home=1, predicted_away=0)

        call_command("seed_test_tournament", verbosity=0)  # rerun must not wipe it

        self.assertTrue(Prediction.objects.filter(membership=mem).exists())
        self.assertEqual(comp.matches.count(), len(sd.TEST_CUP_SCHEDULE))
