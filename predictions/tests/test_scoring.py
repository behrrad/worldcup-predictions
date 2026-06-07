"""
Tests for the scoring engine — the heart of the app.

Tier rules (highest applicable wins), then × stage multiplier:
  exact score ............... points_exact          (default 10)
  right winner + right diff . points_correct_diff   (default 7)
  right winner only ......... points_correct_winner (default 5)
  submitted but wrong ....... points_participation  (default 2)
  no prediction ............. 0
"""
from decimal import Decimal

from django.test import TestCase

from predictions import consts, scoring
from predictions.models import Membership, Prediction

from .factories import join, make_competition, make_league, make_match


class OutcomeSignTests(TestCase):
    def test_signs(self):
        self.assertEqual(scoring.outcome_sign(2, 1), 1)   # home win
        self.assertEqual(scoring.outcome_sign(0, 3), -1)  # away win
        self.assertEqual(scoring.outcome_sign(1, 1), 0)   # draw


class BaseTierTests(TestCase):
    def test_exact(self):
        self.assertEqual(scoring.base_tier(2, 1, 2, 1), consts.Tier.EXACT)

    def test_correct_diff_not_exact(self):
        # predicted 2-1, actual 3-2: same diff (+1), same winner, not exact
        self.assertEqual(scoring.base_tier(2, 1, 3, 2), consts.Tier.DIFF)

    def test_winner_only(self):
        # predicted 1-0, actual 3-1: both home wins, different margins
        self.assertEqual(scoring.base_tier(1, 0, 3, 1), consts.Tier.WINNER)

    def test_wrong_is_participation(self):
        # predicted away win, actual home win
        self.assertEqual(scoring.base_tier(0, 2, 2, 1), consts.Tier.PARTICIPATION)

    def test_draw_exact(self):
        self.assertEqual(scoring.base_tier(1, 1, 1, 1), consts.Tier.EXACT)

    def test_draw_correct_diff(self):
        # predicted 0-0, actual 2-2: same diff (0), draw, not exact -> DIFF
        self.assertEqual(scoring.base_tier(0, 0, 2, 2), consts.Tier.DIFF)

    def test_predicted_draw_actual_win_is_participation(self):
        self.assertEqual(scoring.base_tier(1, 1, 2, 1), consts.Tier.PARTICIPATION)


class ScorePredictionTests(TestCase):
    def setUp(self):
        self.comp = make_competition()
        self.league = make_league(self.comp)  # default scoring 10/7/5/2, knockout 1.5
        self.member = Membership.objects.get(league=self.league)

    def _match(self, home, away, stage=consts.Stage.GROUP):
        m = make_match(self.comp, stage=stage)
        m.home_score, m.away_score = home, away
        m.save()
        return m

    def _pred(self, match, ph, pa):
        return Prediction.objects.create(
            membership=self.member, match=match, predicted_home=ph, predicted_away=pa
        )

    def test_exact_group(self):
        m = self._match(2, 1)
        points, tier = scoring.score_prediction(self.league, m, self._pred(m, 2, 1))
        self.assertEqual(tier, consts.Tier.EXACT)
        self.assertEqual(points, Decimal("10.00"))

    def test_diff_group(self):
        m = self._match(3, 2)
        points, tier = scoring.score_prediction(self.league, m, self._pred(m, 2, 1))
        self.assertEqual(tier, consts.Tier.DIFF)
        self.assertEqual(points, Decimal("7.00"))

    def test_winner_group(self):
        m = self._match(3, 1)
        points, tier = scoring.score_prediction(self.league, m, self._pred(m, 1, 0))
        self.assertEqual(tier, consts.Tier.WINNER)
        self.assertEqual(points, Decimal("5.00"))

    def test_participation_group(self):
        m = self._match(2, 1)
        points, tier = scoring.score_prediction(self.league, m, self._pred(m, 0, 2))
        self.assertEqual(tier, consts.Tier.PARTICIPATION)
        self.assertEqual(points, Decimal("2.00"))

    def test_no_prediction_is_zero(self):
        m = self._match(2, 1)
        points, tier = scoring.score_prediction(self.league, m, None)
        self.assertEqual(tier, consts.Tier.NONE)
        self.assertEqual(points, Decimal("0.00"))

    def test_unfinished_match_returns_none(self):
        m = make_match(self.comp)  # no scores
        self.assertIsNone(scoring.score_prediction(self.league, m, self._pred(m, 1, 0)))

    def test_knockout_multiplier_applies(self):
        # exact score in the final: 10 * 1.5 = 15.00
        m = self._match(2, 1, stage=consts.Stage.FINAL)
        points, tier = scoring.score_prediction(self.league, m, self._pred(m, 2, 1))
        self.assertEqual(tier, consts.Tier.EXACT)
        self.assertEqual(points, Decimal("15.00"))

    def test_participation_multiplied_in_knockout(self):
        # wrong prediction in semi-final: 2 * 1.5 = 3.00
        m = self._match(2, 1, stage=consts.Stage.SEMI)
        points, _ = scoring.score_prediction(self.league, m, self._pred(m, 0, 3))
        self.assertEqual(points, Decimal("3.00"))


class CustomConfigTests(TestCase):
    def test_custom_points_and_multiplier(self):
        comp = make_competition()
        league = make_league(
            comp, points_exact=20, multiplier_final=Decimal("2.0"),
        )
        member = Membership.objects.get(league=league)
        m = make_match(comp, stage=consts.Stage.FINAL)
        m.home_score, m.away_score = 1, 0
        m.save()
        pred = Prediction.objects.create(
            membership=member, match=m, predicted_home=1, predicted_away=0
        )
        points, tier = scoring.score_prediction(league, m, pred)
        self.assertEqual(tier, consts.Tier.EXACT)
        self.assertEqual(points, Decimal("40.00"))  # 20 * 2.0


class RecomputeTests(TestCase):
    def setUp(self):
        self.comp = make_competition()
        self.league = make_league(self.comp)
        self.owner = self.league.owner
        self.member2 = join(self.league).user

    def test_recompute_creates_scores_for_all_members(self):
        m = make_match(self.comp)
        # owner predicts exact, member2 predicts wrong
        own_mem = Membership.objects.get(league=self.league, user=self.owner)
        m2_mem = Membership.objects.get(league=self.league, user=self.member2)
        Prediction.objects.create(membership=own_mem, match=m, predicted_home=1, predicted_away=0)
        Prediction.objects.create(membership=m2_mem, match=m, predicted_home=0, predicted_away=1)
        # enter result -> signal recomputes
        m.home_score, m.away_score = 1, 0
        m.save()

        own_score = own_mem.scores.get(match=m)
        m2_score = m2_mem.scores.get(match=m)
        self.assertEqual(own_score.tier, consts.Tier.EXACT)
        self.assertEqual(own_score.points, Decimal("10.00"))
        self.assertEqual(m2_score.tier, consts.Tier.PARTICIPATION)
        self.assertEqual(m2_score.points, Decimal("2.00"))

    def test_changing_result_recomputes(self):
        m = make_match(self.comp)
        own_mem = Membership.objects.get(league=self.league, user=self.owner)
        Prediction.objects.create(membership=own_mem, match=m, predicted_home=2, predicted_away=0)
        m.home_score, m.away_score = 2, 0
        m.save()
        self.assertEqual(own_mem.scores.get(match=m).tier, consts.Tier.EXACT)
        # correct the result
        m.home_score, m.away_score = 1, 0
        m.save()
        self.assertEqual(own_mem.scores.get(match=m).tier, consts.Tier.WINNER)

    def test_clearing_result_removes_scores(self):
        from predictions.models import MatchScore
        m = make_match(self.comp)
        own_mem = Membership.objects.get(league=self.league, user=self.owner)
        Prediction.objects.create(membership=own_mem, match=m, predicted_home=1, predicted_away=1)
        m.home_score, m.away_score = 1, 1
        m.save()
        self.assertTrue(MatchScore.objects.filter(match=m).exists())
        m.home_score, m.away_score = None, None
        m.save()
        self.assertFalse(MatchScore.objects.filter(match=m).exists())


class LeaderboardTests(TestCase):
    def test_ranking_and_ties(self):
        comp = make_competition()
        league = make_league(comp)
        a = league.owner
        b = join(league).user
        c = join(league).user
        a_mem = Membership.objects.get(league=league, user=a)
        b_mem = Membership.objects.get(league=league, user=b)
        c_mem = Membership.objects.get(league=league, user=c)

        m = make_match(comp)
        Prediction.objects.create(membership=a_mem, match=m, predicted_home=2, predicted_away=1)  # exact 10
        Prediction.objects.create(membership=b_mem, match=m, predicted_home=2, predicted_away=1)  # exact 10
        Prediction.objects.create(membership=c_mem, match=m, predicted_home=0, predicted_away=0)  # wrong 2
        m.home_score, m.away_score = 2, 1
        m.save()

        board = scoring.leaderboard(league)
        # a and b tie at 10 -> both rank 1; c rank 3
        by_user = {row["membership"].user_id: row for row in board}
        self.assertEqual(by_user[a.id]["total"], Decimal("10.00"))
        self.assertEqual(by_user[b.id]["total"], Decimal("10.00"))
        self.assertEqual(by_user[a.id]["rank"], 1)
        self.assertEqual(by_user[b.id]["rank"], 1)
        self.assertEqual(by_user[c.id]["rank"], 3)
        self.assertEqual(by_user[a.id]["exact_count"], 1)
