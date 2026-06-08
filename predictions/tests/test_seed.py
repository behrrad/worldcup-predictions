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

    def test_loads_venues_and_bracket_labels(self):
        call_command("seed_worldcup2026", verbosity=0)
        comp = Competition.objects.get(slug=sd.WC2026_SLUG)
        # every match has a venue
        self.assertTrue(all(m.venue for m in comp.matches.all()))
        # group matches have real teams, so no bracket labels
        opener = comp.matches.get(match_number=1)
        self.assertTrue(opener.venue)
        self.assertEqual(opener.home_label, "")
        # knockout matches carry English bracket-slot labels (translated in the API)
        ko = comp.matches.get(match_number=73)
        self.assertTrue(ko.home_label and ko.away_label)


class BracketLabelTranslationTests(TestCase):
    def test_translates_known_patterns(self):
        cases = {
            "Group A Winner": "صدرنشین گروه A",
            "Group L Runner-up": "نایب‌قهرمان گروه L",
            "Group A/B/C/D/F 3rd Place": "تیم سوم از گروه‌های A/B/C/D/F",
            "Match 73 Winner": "برندهٔ بازی ۷۳",
            "Match 101 Loser": "بازندهٔ بازی ۱۰۱",
        }
        for raw, expected in cases.items():
            self.assertEqual(consts.bracket_label_fa(raw), expected)

    def test_empty_label_is_unknown(self):
        self.assertEqual(consts.bracket_label_fa(""), consts.BRACKET_UNKNOWN)

    def test_unknown_pattern_is_echoed(self):
        self.assertEqual(consts.bracket_label_fa("Some New Slot"), "Some New Slot")

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

    def test_rejects_invalid_knockout_team_code(self):
        """A non-null team code on any match (incl. knockout) must be a real team."""
        from predictions.management.commands.seed_worldcup2026 import DATA_PATH
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        ko = next(m for m in data["matches"] if m["stage"] != "GROUP")
        ko["home_code"] = "XXX"  # typo: not a real team code
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            bad_path = f.name
        with self.assertRaises(CommandError):
            call_command("seed_worldcup2026", "--file", bad_path, verbosity=0)

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

    def test_pruned_knockout_team_reverts_slot_and_clears_data(self):
        """An admin-filled knockout team that's pruned on reload reverts the slot to
        undecided and clears the stale result/prediction (it can't stay attached)."""
        call_command("seed_worldcup2026", verbosity=0)
        comp = Competition.objects.get(slug=sd.WC2026_SLUG)
        ghost = Team.objects.create(competition=comp, name_fa="حذف‌شده", name_en="Gone",
                                    code="ZZZ", group="")
        ko = comp.matches.exclude(stage=consts.Stage.GROUP).order_by("match_number").first()
        ko.home_team = ghost
        ko.home_score, ko.away_score = 1, 0
        ko.save()
        user = User.objects.create_user(email="k@test.com", password="pw")
        league = League.objects.create(name="L", competition=comp, owner=user)
        mem = Membership.objects.create(league=league, user=user, role=consts.Role.OWNER)
        Prediction.objects.create(membership=mem, match=ko, predicted_home=1, predicted_away=0)

        call_command("seed_worldcup2026", verbosity=0)  # reload prunes the ghost

        ko.refresh_from_db()
        self.assertFalse(comp.teams.filter(code="ZZZ").exists())        # ghost pruned
        self.assertIsNone(ko.home_team_id)                             # slot back to undecided
        self.assertIsNone(ko.home_score)                              # stale result cleared
        self.assertFalse(Prediction.objects.filter(match=ko).exists())


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


class RevealDemoCommandTests(TestCase):
    """`seed_reveal_demo` builds a full league (owner + members + predictions)
    with one match in every state, for exercising the reveal toggle + lock."""

    def _comp_and_league(self):
        comp = Competition.objects.get(slug=sd.REVEAL_DEMO_COMP_SLUG)
        league = League.objects.get(competition=comp, name=sd.REVEAL_DEMO_LEAGUE_NAME)
        return comp, league

    def test_builds_full_demo_league(self):
        call_command("seed_reveal_demo", verbosity=0)
        comp, league = self._comp_and_league()
        # Owner + all bot members are joined.
        self.assertEqual(league.owner.email, sd.REVEAL_DEMO_OWNER_EMAIL)
        self.assertEqual(league.memberships.count(), 1 + len(sd.REVEAL_DEMO_MEMBERS))
        # Reveal defaults to on so the owner can demo turning it off.
        self.assertTrue(league.reveal_predictions)
        # Every member predicted every match.
        self.assertEqual(
            Prediction.objects.filter(match__competition=comp).count(),
            len(sd.REVEAL_DEMO_PREDICTIONS) * len(sd.REVEAL_DEMO_SCHEDULE),
        )

    def test_covers_every_match_state(self):
        from django.utils import timezone

        call_command("seed_reveal_demo", verbosity=0)
        comp, _ = self._comp_and_league()
        now = timezone.now()
        matches = list(comp.matches.order_by("match_number"))
        finished = [m for m in matches if m.is_finished]
        open_ = [m for m in matches if not m.is_finished and m.is_open_for(30, now)]
        locked = [m for m in matches
                  if not m.is_finished and not m.is_open_for(30, now)]
        started = [m for m in locked if m.kickoff <= now]
        self.assertEqual(len(finished), 1)      # the -2h match
        self.assertEqual(len(open_), 1)         # the +2h match
        self.assertEqual(len(locked), 2)        # +10m (pre-kickoff) and -20m (started)
        self.assertTrue(started)                # at least one already kicked off

    def test_finished_match_is_scored(self):
        from predictions import scoring

        call_command("seed_reveal_demo", verbosity=0)
        _, league = self._comp_and_league()
        rows = scoring.leaderboard(league)
        top = rows[0]
        # Owner predicted the exact 2-1 final result: 10 × 1.5 (final) = 15.
        self.assertEqual(top["membership"].user.email, sd.REVEAL_DEMO_OWNER_EMAIL)
        self.assertEqual(float(top["total"]), 15.0)

    def test_custom_owner_email(self):
        call_command("seed_reveal_demo", "--owner-email", "owner@example.com",
                     verbosity=0)
        league = League.objects.get(name=sd.REVEAL_DEMO_LEAGUE_NAME)
        self.assertEqual(league.owner.email, "owner@example.com")

    def test_rerun_is_idempotent(self):
        call_command("seed_reveal_demo", verbosity=0)
        call_command("seed_reveal_demo", verbosity=0)  # refresh timings, no dupes
        self.assertEqual(
            League.objects.filter(name=sd.REVEAL_DEMO_LEAGUE_NAME).count(), 1
        )
        comp, _ = self._comp_and_league()
        self.assertEqual(comp.matches.count(), len(sd.REVEAL_DEMO_SCHEDULE))
        self.assertEqual(
            Prediction.objects.filter(match__competition=comp).count(),
            len(sd.REVEAL_DEMO_PREDICTIONS) * len(sd.REVEAL_DEMO_SCHEDULE),
        )
