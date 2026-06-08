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


class SeedCommandTests(TestCase):
    """`seed_worldcup2026` loads the real, official 2026 schedule by default."""

    def test_seed_creates_expected_counts(self):
        call_command("seed_worldcup2026", verbosity=0)
        comp = Competition.objects.get(slug=sd.WC2026_SLUG)
        # 12 groups × 4 teams = 48
        self.assertEqual(Team.objects.filter(competition=comp).count(), 48)
        # 12 groups × 6 round-robin matches = 72 group matches
        group = Match.objects.filter(competition=comp, stage=consts.Stage.GROUP)
        self.assertEqual(group.count(), 72)
        # knockout: 16+8+4+2+1+1 = 32
        knockout = Match.objects.filter(competition=comp).exclude(stage=consts.Stage.GROUP)
        self.assertEqual(knockout.count(), 32)

    def test_group_matches_have_both_teams(self):
        call_command("seed_worldcup2026", verbosity=0)
        comp = Competition.objects.get(slug=sd.WC2026_SLUG)
        group = comp.matches.filter(stage=consts.Stage.GROUP)
        self.assertTrue(all(m.home_team_id and m.away_team_id for m in group))

    def test_every_match_has_a_kickoff(self):
        call_command("seed_worldcup2026", verbosity=0)
        comp = Competition.objects.get(slug=sd.WC2026_SLUG)
        self.assertTrue(all(m.kickoff is not None for m in comp.matches.all()))

    def test_loads_real_opener(self):
        """The real schedule opens with Mexico v South Africa at the Azteca."""
        call_command("seed_worldcup2026", verbosity=0)
        comp = Competition.objects.get(slug=sd.WC2026_SLUG)
        opener = comp.matches.get(match_number=1)
        self.assertEqual(opener.home_team.code, "MEX")
        self.assertEqual(opener.away_team.code, "RSA")

    def test_iran_is_seeded(self):
        call_command("seed_worldcup2026", verbosity=0)
        self.assertTrue(Team.objects.filter(name_fa="ایران", group="G").exists())

    def test_seed_is_idempotent(self):
        call_command("seed_worldcup2026", verbosity=0)
        call_command("seed_worldcup2026", verbosity=0)  # re-runs upsert to the same state
        comp = Competition.objects.get(slug=sd.WC2026_SLUG)
        self.assertEqual(Team.objects.filter(competition=comp).count(), 48)
        self.assertEqual(Match.objects.filter(competition=comp).count(), 104)

    def test_reload_preserves_predictions_and_results(self):
        """A second load must NOT wipe predictions/scores/results (upsert by number)."""
        call_command("seed_worldcup2026", verbosity=0)
        comp = Competition.objects.get(slug=sd.WC2026_SLUG)
        user = User.objects.create_user(email="p@test.com", password="pw")
        league = League.objects.create(name="L", competition=comp, owner=user)
        mem = Membership.objects.create(league=league, user=user, role=consts.Role.OWNER)
        match = comp.matches.filter(stage=consts.Stage.GROUP).order_by("match_number").first()
        Prediction.objects.create(membership=mem, match=match,
                                  predicted_home=2, predicted_away=1)
        match_id = match.id

        call_command("seed_worldcup2026", verbosity=0)  # reload

        self.assertTrue(Prediction.objects.filter(membership=mem).exists())
        # the same match row is reused (id preserved), so predictions stay attached
        self.assertTrue(comp.matches.filter(id=match_id).exists())
        self.assertEqual(comp.matches.count(), 104)

    def test_reset_rebuilds_from_scratch(self):
        call_command("seed_worldcup2026", verbosity=0)
        call_command("seed_worldcup2026", "--reset", verbosity=0)
        comp = Competition.objects.get(slug=sd.WC2026_SLUG)
        self.assertEqual(comp.teams.count(), 48)
        self.assertEqual(comp.matches.count(), 104)

    def test_invalid_file_is_rejected_without_mutating(self):
        """A bad file must raise and leave existing data untouched."""
        call_command("seed_worldcup2026", verbosity=0)
        before = Competition.objects.get(slug=sd.WC2026_SLUG).matches.count()

        bad = {"competition": {"slug": sd.WC2026_SLUG}, "teams": [], "matches": []}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(bad, f)
            bad_path = f.name

        with self.assertRaises(CommandError):
            call_command("seed_worldcup2026", "--file", bad_path, verbosity=0)

        after = Competition.objects.get(slug=sd.WC2026_SLUG).matches.count()
        self.assertEqual(before, after)  # nothing was deleted

    def test_reload_preserves_filled_knockout_teams(self):
        """An admin fills a knockout match's teams; a reload must NOT wipe them."""
        from predictions.management.commands.seed_worldcup2026 import DATA_PATH
        call_command("seed_worldcup2026", verbosity=0)
        comp = Competition.objects.get(slug=sd.WC2026_SLUG)
        ko = comp.matches.exclude(stage=consts.Stage.GROUP).order_by("match_number").first()
        self.assertIsNone(ko.home_team_id)  # starts undecided
        home, away = comp.teams.all()[0], comp.teams.all()[1]
        ko.home_team, ko.away_team = home, away
        ko.save()

        call_command("seed_worldcup2026", "--file", str(DATA_PATH), verbosity=0)  # reload

        ko.refresh_from_db()
        self.assertEqual(ko.home_team_id, home.id)
        self.assertEqual(ko.away_team_id, away.id)

    def test_rejects_wrong_match_number_set(self):
        """104 matches whose numbers aren't exactly 1..104 are rejected (no stale rows)."""
        from predictions.management.commands.seed_worldcup2026 import DATA_PATH
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        data["matches"][0]["match_number"] = 999  # breaks the 1..104 set
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            bad_path = f.name
        with self.assertRaises(CommandError):
            call_command("seed_worldcup2026", "--file", bad_path, verbosity=0)

    def test_changed_fixture_clears_only_its_stale_predictions(self):
        """Migrating a match number to a different pairing drops its stale
        predictions; matches whose fixture is unchanged keep theirs."""
        from predictions.management.commands.seed_worldcup2026 import DATA_PATH
        call_command("seed_worldcup2026", verbosity=0)
        comp = Competition.objects.get(slug=sd.WC2026_SLUG)
        user = User.objects.create_user(email="m@test.com", password="pw")
        league = League.objects.create(name="L", competition=comp, owner=user)
        mem = Membership.objects.create(league=league, user=user, role=consts.Role.OWNER)
        m1, m2 = comp.matches.get(match_number=1), comp.matches.get(match_number=2)
        Prediction.objects.create(membership=mem, match=m1, predicted_home=1, predicted_away=0)
        Prediction.objects.create(membership=mem, match=m2, predicted_home=2, predicted_away=2)

        # Repoint match #1 at a different pairing; leave #2 unchanged.
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        by_num = {x["match_number"]: x for x in data["matches"]}
        used = {by_num[1]["home_code"], by_num[1]["away_code"]}
        others = [t["code"] for t in data["teams"] if t["code"] not in used][:2]
        by_num[1]["home_code"], by_num[1]["away_code"] = others
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name

        call_command("seed_worldcup2026", "--file", path, verbosity=0)

        self.assertFalse(Prediction.objects.filter(match=m1).exists())  # fixture changed
        self.assertTrue(Prediction.objects.filter(match=m2).exists())   # unchanged

    def test_migration_from_pruned_old_team_clears_stale_data(self):
        """Old placeholder fixture using a team not in the real JSON: the team is
        pruned, yet the stale prediction AND result are still cleared."""
        call_command("seed_worldcup2026", verbosity=0)
        comp = Competition.objects.get(slug=sd.WC2026_SLUG)
        # A "ghost" team whose code isn't in the real 2026 field (e.g. old fake data).
        ghost = Team.objects.create(competition=comp, name_fa="قدیمی", name_en="Old",
                                    code="CHI", group="A")
        m1 = comp.matches.get(match_number=1)
        m1.home_team = ghost
        m1.home_score, m1.away_score = 3, 0  # admin had entered a result
        m1.save()
        user = User.objects.create_user(email="g@test.com", password="pw")
        league = League.objects.create(name="L", competition=comp, owner=user)
        mem = Membership.objects.create(league=league, user=user, role=consts.Role.OWNER)
        Prediction.objects.create(membership=mem, match=m1, predicted_home=3, predicted_away=0)

        call_command("seed_worldcup2026", verbosity=0)  # real reload prunes CHI

        m1.refresh_from_db()
        self.assertFalse(comp.teams.filter(code="CHI").exists())        # ghost pruned
        self.assertFalse(Prediction.objects.filter(match=m1).exists())  # stale prediction cleared
        self.assertIsNone(m1.home_score)                               # stale result cleared
        self.assertFalse(m1.is_finished)
        self.assertEqual(m1.home_team.code, "MEX")                     # now the real fixture


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
