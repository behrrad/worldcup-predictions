from collections import Counter

from django.core.management import call_command
from django.test import TestCase

from predictions import seed_data as sd
from predictions.models import Competition, Match, Team


class LoadRealScheduleTests(TestCase):
    def test_loads_full_2026_schedule(self):
        call_command("load_worldcup2026", verbosity=0)
        comp = Competition.objects.get(slug=sd.WC2026_SLUG)
        self.assertEqual(comp.teams.count(), 48)
        self.assertEqual(comp.matches.count(), 104)
        by_stage = Counter(m.stage for m in comp.matches.all())
        self.assertEqual(by_stage["GROUP"], 72)
        self.assertEqual(sum(v for k, v in by_stage.items() if k != "GROUP"), 32)

    def test_group_matches_have_both_teams(self):
        call_command("load_worldcup2026", verbosity=0)
        comp = Competition.objects.get(slug=sd.WC2026_SLUG)
        group = comp.matches.filter(stage="GROUP")
        self.assertTrue(all(m.home_team_id and m.away_team_id for m in group))

    def test_every_match_has_a_kickoff(self):
        call_command("load_worldcup2026", verbosity=0)
        comp = Competition.objects.get(slug=sd.WC2026_SLUG)
        self.assertTrue(all(m.kickoff is not None for m in comp.matches.all()))

    def test_iran_is_present(self):
        call_command("load_worldcup2026", verbosity=0)
        self.assertTrue(Team.objects.filter(name_fa="ایران", group="G").exists())

    def test_reload_is_idempotent(self):
        call_command("load_worldcup2026", verbosity=0)
        call_command("load_worldcup2026", verbosity=0)
        comp = Competition.objects.get(slug=sd.WC2026_SLUG)
        self.assertEqual(comp.matches.count(), 104)
        self.assertEqual(comp.teams.count(), 48)
