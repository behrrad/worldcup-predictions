from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from predictions import consts
from predictions.models import generate_invite_code

from .factories import make_competition, make_league, make_match


class InviteCodeTests(TestCase):
    def test_length_and_alphabet(self):
        code = generate_invite_code()
        self.assertEqual(len(code), consts.INVITE_CODE_LENGTH)
        self.assertTrue(all(c in consts.INVITE_CODE_ALPHABET for c in code))

    def test_codes_are_unique_per_league(self):
        comp = make_competition()
        a = make_league(comp, name="A")
        b = make_league(comp, name="B")
        self.assertNotEqual(a.invite_code, b.invite_code)


class SlugTests(TestCase):
    def test_persian_slug_generated(self):
        comp = make_competition(name="جام جهانی")
        league = make_league(comp, name="رفقای فوتبال")
        self.assertTrue(league.slug)  # unicode slug allowed
        self.assertIn("رفقای", league.slug)


class MultiplierTests(TestCase):
    def test_defaults(self):
        league = make_league(make_competition())
        self.assertEqual(league.multiplier_for(consts.Stage.GROUP), Decimal("1.0"))
        self.assertEqual(league.multiplier_for(consts.Stage.FINAL), Decimal("1.5"))
        self.assertEqual(league.multiplier_for(consts.Stage.QUARTER), Decimal("1.5"))

    def test_unknown_stage_defaults_to_group(self):
        league = make_league(make_competition())
        self.assertEqual(league.multiplier_for("UNKNOWN"), consts.DEFAULT_GROUP_MULTIPLIER)


class MatchStatusTests(TestCase):
    def test_entering_scores_marks_finished(self):
        m = make_match(make_competition())
        self.assertFalse(m.is_finished)
        self.assertEqual(m.status, consts.MatchStatus.SCHEDULED)
        m.home_score, m.away_score = 1, 0
        m.save()
        self.assertTrue(m.is_finished)
        self.assertEqual(m.status, consts.MatchStatus.FINISHED)

    def test_partial_score_is_not_finished(self):
        m = make_match(make_competition())
        m.home_score = 1  # only one side
        m.save()
        self.assertFalse(m.has_result)
        self.assertFalse(m.is_finished)


class LockWindowTests(TestCase):
    def setUp(self):
        self.comp = make_competition()
        self.now = timezone.now()

    def test_open_well_before_kickoff(self):
        m = make_match(self.comp, kickoff=self.now + timedelta(hours=2))
        self.assertTrue(m.is_open_for(30, now=self.now))

    def test_closed_inside_lock_window(self):
        # kickoff in 10 min, lock is 30 min before -> already closed
        m = make_match(self.comp, kickoff=self.now + timedelta(minutes=10))
        self.assertFalse(m.is_open_for(30, now=self.now))

    def test_closed_after_kickoff(self):
        m = make_match(self.comp, kickoff=self.now - timedelta(minutes=5))
        self.assertFalse(m.is_open_for(30, now=self.now))

    def test_finished_match_is_closed(self):
        m = make_match(self.comp, kickoff=self.now + timedelta(hours=2))
        m.home_score, m.away_score = 1, 1
        m.save()
        self.assertFalse(m.is_open_for(30, now=self.now))

    def test_lock_time_calculation(self):
        kickoff = self.now + timedelta(hours=1)
        m = make_match(self.comp, kickoff=kickoff)
        self.assertEqual(m.lock_time(30), kickoff - timedelta(minutes=30))
