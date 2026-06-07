import json
import tempfile
from collections import Counter

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from accounts.models import User
from predictions import consts, seed_data as sd
from predictions.models import (
    Competition,
    League,
    Match,
    Membership,
    Prediction,
    Team,
)


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

    def test_reload_preserves_predictions_and_results(self):
        """A second load must NOT wipe predictions/scores/results (Codex P1)."""
        call_command("load_worldcup2026", verbosity=0)
        comp = Competition.objects.get(slug=sd.WC2026_SLUG)
        user = User.objects.create_user(email="p@test.com", password="pw")
        league = League.objects.create(name="L", competition=comp, owner=user)
        mem = Membership.objects.create(league=league, user=user, role=consts.Role.OWNER)
        match = comp.matches.filter(stage="GROUP").order_by("match_number").first()
        Prediction.objects.create(membership=mem, match=match,
                                  predicted_home=2, predicted_away=1)
        match_id = match.id

        call_command("load_worldcup2026", verbosity=0)  # reload

        self.assertTrue(Prediction.objects.filter(membership=mem).exists())
        # the same match row is reused (id preserved), so predictions stay attached
        self.assertTrue(comp.matches.filter(id=match_id).exists())
        self.assertEqual(comp.matches.count(), 104)

    def test_invalid_file_is_rejected_without_mutating(self):
        """A bad file must raise and leave existing data untouched (Codex P2)."""
        call_command("load_worldcup2026", verbosity=0)
        before = Competition.objects.get(slug=sd.WC2026_SLUG).matches.count()

        bad = {"competition": {"slug": sd.WC2026_SLUG}, "teams": [], "matches": []}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(bad, f)
            bad_path = f.name

        with self.assertRaises(CommandError):
            call_command("load_worldcup2026", "--file", bad_path, verbosity=0)

        after = Competition.objects.get(slug=sd.WC2026_SLUG).matches.count()
        self.assertEqual(before, after)  # nothing was deleted
