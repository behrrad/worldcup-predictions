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
