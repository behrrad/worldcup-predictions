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

    def test_boost_doubles_qf_onward(self):
        # After opting in, an exact QF score scores 10 * 2.0 = 20.00.
        self.league.apply_boost()
        for stage in consts.BOOST_STAGES:
            m = self._match(2, 1, stage=stage)
            points, tier = scoring.score_prediction(self.league, m, self._pred(m, 2, 1))
            self.assertEqual(tier, consts.Tier.EXACT)
            self.assertEqual(points, Decimal("20.00"), stage)

    def test_custom_boost_multiplier_applies(self):
        # A custom 2.5× set by the owner: exact QF score scores 10 * 2.5 = 25.00.
        self.league.set_boost_multiplier(Decimal("2.5"))
        m = self._match(2, 1, stage=consts.Stage.QUARTER)
        points, tier = scoring.score_prediction(self.league, m, self._pred(m, 2, 1))
        self.assertEqual(tier, consts.Tier.EXACT)
        self.assertEqual(points, Decimal("25.00"))
        self.assertEqual(self.league.boost_decision, consts.BoostDecision.ACCEPTED)

    def test_boost_leaves_group_stage_untouched(self):
        self.league.apply_boost()
        m = self._match(2, 1, stage=consts.Stage.GROUP)
        points, _ = scoring.score_prediction(self.league, m, self._pred(m, 2, 1))
        self.assertEqual(points, Decimal("10.00"))  # group ×1.0, unchanged

    def test_boost_does_not_touch_earlier_knockout_rounds(self):
        # R32/R16 keep the default 1.5× — the boost is QF-onward only.
        self.league.apply_boost()
        m = self._match(2, 1, stage=consts.Stage.ROUND_OF_16)
        points, _ = scoring.score_prediction(self.league, m, self._pred(m, 2, 1))
        self.assertEqual(points, Decimal("15.00"))

    def test_decline_keeps_default_knockout_multiplier(self):
        self.league.decline_boost()
        m = self._match(2, 1, stage=consts.Stage.QUARTER)
        points, _ = scoring.score_prediction(self.league, m, self._pred(m, 2, 1))
        self.assertEqual(points, Decimal("15.00"))  # still 10 * 1.5
        self.assertEqual(self.league.boost_decision, consts.BoostDecision.DECLINED)


class PenaltyShootoutTests(TestCase):
    """Knockout matches level at 120' and decided on penalties.

    The 120' draw is scored against home_score/away_score; the shootout winner
    (Match.penalty_winner) lifts a draw prediction onto a higher tier when the
    member also picked the right side to advance. Only draw predictions can earn
    the bonus, and only when the game actually goes to penalties.
    """

    def setUp(self):
        self.comp = make_competition()
        self.league = make_league(self.comp)  # 10/7/5/2, knockout ×1.5
        self.member = Membership.objects.get(league=self.league)

    def _pen_match(self, home, away, winner, stage=consts.Stage.ROUND_OF_16):
        """A finished knockout match level at home-away, decided on penalties
        for `winner` (HOME/AWAY)."""
        m = make_match(self.comp, stage=stage)
        m.home_score, m.away_score = home, away
        m.penalty_winner = winner
        m.save()
        return m

    def _pred(self, match, ph, pa, advancer=consts.Advancer.NONE):
        return Prediction.objects.create(
            membership=self.member, match=match,
            predicted_home=ph, predicted_away=pa, predicted_advancer=advancer,
        )

    def test_exact_draw_right_advancer_is_exact(self):
        m = self._pen_match(1, 1, consts.Advancer.HOME)
        points, tier = scoring.score_prediction(
            self.league, m, self._pred(m, 1, 1, consts.Advancer.HOME))
        self.assertEqual(tier, consts.Tier.EXACT)
        self.assertEqual(points, Decimal("15.00"))  # 10 × 1.5

    def test_exact_draw_wrong_advancer_is_diff(self):
        m = self._pen_match(1, 1, consts.Advancer.AWAY)
        points, tier = scoring.score_prediction(
            self.league, m, self._pred(m, 1, 1, consts.Advancer.HOME))
        self.assertEqual(tier, consts.Tier.DIFF)
        self.assertEqual(points, Decimal("10.50"))  # 7 × 1.5

    def test_other_draw_right_advancer_is_diff(self):
        # Right that it's a draw and who advances, wrong exact scoreline.
        m = self._pen_match(1, 1, consts.Advancer.HOME)
        points, tier = scoring.score_prediction(
            self.league, m, self._pred(m, 0, 0, consts.Advancer.HOME))
        self.assertEqual(tier, consts.Tier.DIFF)
        self.assertEqual(points, Decimal("10.50"))

    def test_other_draw_wrong_advancer_is_winner(self):
        m = self._pen_match(1, 1, consts.Advancer.AWAY)
        points, tier = scoring.score_prediction(
            self.league, m, self._pred(m, 2, 2, consts.Advancer.HOME))
        self.assertEqual(tier, consts.Tier.WINNER)
        self.assertEqual(points, Decimal("7.50"))  # 5 × 1.5

    def test_exact_draw_without_advancer_pick_caps_at_diff(self):
        # An exact draw with no advancer picked can't be EXACT (advancer wrong),
        # so it lands at DIFF — never the top tier.
        m = self._pen_match(1, 1, consts.Advancer.HOME)
        points, tier = scoring.score_prediction(
            self.league, m, self._pred(m, 1, 1, consts.Advancer.NONE))
        self.assertEqual(tier, consts.Tier.DIFF)
        self.assertEqual(points, Decimal("10.50"))

    def test_non_draw_prediction_is_participation(self):
        # Backed a winner but the match was level at 120' — wrong outcome, no
        # advancer credit even if the predicted winner went on to advance.
        m = self._pen_match(1, 1, consts.Advancer.HOME)
        points, tier = scoring.score_prediction(
            self.league, m, self._pred(m, 2, 1))
        self.assertEqual(tier, consts.Tier.PARTICIPATION)
        self.assertEqual(points, Decimal("3.00"))  # 2 × 1.5

    def test_draw_pick_in_game_decided_in_regulation_is_participation(self):
        # The note: a draw prediction earns >2 ONLY when the game goes to pens.
        # Here the knockout was decided in normal/extra time (2-1, no shootout).
        m = make_match(self.comp, stage=consts.Stage.ROUND_OF_16)
        m.home_score, m.away_score = 2, 1
        m.save()
        points, tier = scoring.score_prediction(
            self.league, m, self._pred(m, 1, 1, consts.Advancer.HOME))
        self.assertEqual(tier, consts.Tier.PARTICIPATION)
        self.assertEqual(points, Decimal("3.00"))

    def test_group_match_never_uses_penalty_rules(self):
        # Group games can't go to penalties; a stray penalty_winner is ignored,
        # so an exact draw scores the normal EXACT tier (×1.0).
        m = make_match(self.comp, stage=consts.Stage.GROUP)
        m.home_score, m.away_score = 1, 1
        m.penalty_winner = consts.Advancer.HOME  # nonsensical for a group game
        m.save()
        points, tier = scoring.score_prediction(
            self.league, m, self._pred(m, 1, 1, consts.Advancer.AWAY))
        self.assertEqual(tier, consts.Tier.EXACT)
        self.assertEqual(points, Decimal("10.00"))

    def test_knockout_draw_without_winner_scores_normally(self):
        # A knockout recorded as a draw but with no penalty_winner yet (result
        # synced before the shootout split arrived) falls back to normal scoring.
        m = make_match(self.comp, stage=consts.Stage.QUARTER)
        m.home_score, m.away_score = 0, 0
        m.save()
        points, tier = scoring.score_prediction(
            self.league, m, self._pred(m, 0, 0))
        self.assertEqual(tier, consts.Tier.EXACT)
        self.assertEqual(points, Decimal("15.00"))

    def test_penalty_result_recomputes_via_signal(self):
        # End-to-end: a prediction exists, then the penalty result is saved —
        # the post_save signal must write the right MatchScore.
        m = make_match(self.comp, stage=consts.Stage.SEMI)
        self._pred(m, 1, 1, consts.Advancer.AWAY)
        m.home_score, m.away_score = 1, 1
        m.penalty_winner = consts.Advancer.AWAY
        m.save()
        score = self.member.scores.get(match=m)
        self.assertEqual(score.tier, consts.Tier.EXACT)
        self.assertEqual(score.points, Decimal("15.00"))


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


class CountForScoringTests(TestCase):
    """A match with count_for_scoring=False is voided: predictions and the
    result are kept, but it contributes no points and is invisible to the
    leaderboard / averages / live view."""

    def setUp(self):
        self.comp = make_competition()
        self.league = make_league(self.comp)
        self.member = Membership.objects.get(league=self.league)

    def _finished_match(self, count_for_scoring=True):
        from predictions.models import MatchScore
        m = make_match(self.comp, count_for_scoring=count_for_scoring)
        Prediction.objects.create(
            membership=self.member, match=m, predicted_home=1, predicted_away=0,
        )
        m.home_score, m.away_score = 1, 0  # would be an exact hit (10 pts)
        m.save()
        return m, MatchScore

    def test_voided_match_writes_no_scores(self):
        m, MatchScore = self._finished_match(count_for_scoring=False)
        self.assertFalse(MatchScore.objects.filter(match=m).exists())
        # The prediction and the result are untouched.
        self.assertTrue(Prediction.objects.filter(match=m).exists())
        self.assertTrue(m.is_finished)

    def test_toggling_off_deletes_existing_scores(self):
        m, MatchScore = self._finished_match(count_for_scoring=True)
        self.assertTrue(MatchScore.objects.filter(match=m).exists())
        m.count_for_scoring = False
        m.save()  # post-save recompute should drop the stale scores
        self.assertFalse(MatchScore.objects.filter(match=m).exists())

    def test_toggling_back_on_rescores(self):
        m, MatchScore = self._finished_match(count_for_scoring=False)
        m.count_for_scoring = True
        m.save()
        score = MatchScore.objects.get(match=m, membership=self.member)
        self.assertEqual(score.tier, consts.Tier.EXACT)
        self.assertEqual(score.points, Decimal("10.00"))

    def test_voided_match_excluded_from_leaderboard(self):
        scored, _ = self._finished_match(count_for_scoring=True)        # 10 pts
        voided = make_match(self.comp, count_for_scoring=False)
        Prediction.objects.create(
            membership=self.member, match=voided, predicted_home=2, predicted_away=2,
        )
        voided.home_score, voided.away_score = 2, 2
        voided.save()

        row = {r["membership"].id: r for r in scoring.leaderboard(self.league)}[self.member.id]
        self.assertEqual(row["total"], Decimal("10.00"))  # only the scored match
        self.assertEqual(row["played"], 1)                # voided game not counted

    def test_voided_match_not_in_average_denominator(self):
        # Member predicts the one scored match; a voided finished match must not
        # inflate the "finished games" denominator that gates average eligibility.
        self._finished_match(count_for_scoring=True)
        voided = make_match(self.comp, count_for_scoring=False)
        voided.home_score, voided.away_score = 0, 0
        voided.save()

        row = {r["membership"].id: r for r in scoring.leaderboard(self.league)}[self.member.id]
        # 1 predicted of 1 counted finished game -> eligible; avg is the full 10.
        self.assertTrue(row["eligible_for_avg"])
        self.assertEqual(row["avg_points"], Decimal("10.0000"))

    def test_recompute_league_skips_voided(self):
        from predictions.models import MatchScore
        m, _ = self._finished_match(count_for_scoring=False)
        # A league-wide recompute (e.g. after settings change) must not resurrect
        # scores for a voided match.
        scoring.recompute_league_scores(self.league)
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

    def test_played_counts_only_predicted_games(self):
        # A finished match writes a MatchScore row for *every* member (tier=NONE
        # for non-predictors), so "played" must exclude those NONE rows.
        comp = make_competition()
        league = make_league(comp)
        predictor = Membership.objects.get(league=league, user=league.owner)
        bystander = join(league)  # in the league but never predicts

        m1 = make_match(comp)
        m2 = make_match(comp)
        Prediction.objects.create(membership=predictor, match=m1, predicted_home=2, predicted_away=1)
        # predictor skips m2; bystander predicts nothing.
        for m, (h, a) in ((m1, (2, 1)), (m2, (0, 0))):
            m.home_score, m.away_score = h, a
            m.save()

        by_id = {row["membership"].id: row for row in scoring.leaderboard(league)}
        # Both matches finished, but predictor only predicted one and bystander none.
        self.assertEqual(by_id[predictor.id]["played"], 1)
        self.assertEqual(by_id[bystander.id]["played"], 0)

    def test_average_eligibility_and_ranking(self):
        # Average view: only members who predicted >= 50% of the finished games
        # are ranked, ordered by points-per-predicted-game.
        comp = make_competition()
        league = make_league(comp)
        a = Membership.objects.get(league=league, user=league.owner)
        b = join(league)
        c = join(league)

        ms = [make_match(comp) for _ in range(4)]
        # a predicts all 4: three exact (10 each) + one wrong winner (2) = 32.
        for m in ms[:3]:
            Prediction.objects.create(membership=a, match=m, predicted_home=1, predicted_away=0)
        Prediction.objects.create(membership=a, match=ms[3], predicted_home=0, predicted_away=2)
        # b predicts 2 (exactly 50%): both exact = 20.
        for m in ms[:2]:
            Prediction.objects.create(membership=b, match=m, predicted_home=1, predicted_away=0)
        # c predicts only 1 (25%): below the bar.
        Prediction.objects.create(membership=c, match=ms[0], predicted_home=1, predicted_away=0)
        for m in ms:
            m.home_score, m.away_score = 1, 0
            m.save()

        by_id = {row["membership"].id: row for row in scoring.leaderboard(league)}
        self.assertEqual(by_id[a.id]["avg_points"], Decimal("8.0000"))   # 32 / 4
        self.assertEqual(by_id[b.id]["avg_points"], Decimal("10.0000"))  # 20 / 2
        # a & b cleared half of the 4 finished games; c (1 of 4) did not.
        self.assertTrue(by_id[a.id]["eligible_for_avg"])
        self.assertTrue(by_id[b.id]["eligible_for_avg"])
        self.assertFalse(by_id[c.id]["eligible_for_avg"])
        # Ranked by average: b (10) ahead of a (8); c unranked.
        self.assertEqual(by_id[b.id]["avg_rank"], 1)
        self.assertEqual(by_id[a.id]["avg_rank"], 2)
        self.assertIsNone(by_id[c.id]["avg_rank"])

    def test_average_rounds_to_four_decimals(self):
        comp = make_competition()
        league = make_league(comp)
        a = Membership.objects.get(league=league, user=league.owner)
        ms = [make_match(comp) for _ in range(3)]
        # one exact (10) + two wrong-but-submitted (2 each) = 14 over 3 games.
        Prediction.objects.create(membership=a, match=ms[0], predicted_home=1, predicted_away=0)
        for m in ms[1:]:
            Prediction.objects.create(membership=a, match=m, predicted_home=0, predicted_away=2)
        for m in ms:
            m.home_score, m.away_score = 1, 0
            m.save()

        row = {r["membership"].id: r for r in scoring.leaderboard(league)}[a.id]
        self.assertEqual(row["total"], Decimal("14.00"))
        self.assertEqual(row["avg_points"], Decimal("4.6667"))  # 14 / 3, 4 dp

    def test_member_without_scores_ranks_last(self):
        # A member with no MatchScore rows (Sum -> NULL) must order as 0, not
        # float to the top. On Postgres NULL sorts first under "-total", so
        # without Coalesce the scoreless member would wrongly outrank a scorer.
        # (SQLite sorts NULL last, so this guards the intended behavior either way.)
        comp = make_competition()
        league = make_league(comp)
        scorer = league.owner
        scorer_mem = Membership.objects.get(league=league, user=scorer)

        m = make_match(comp)
        Prediction.objects.create(membership=scorer_mem, match=m, predicted_home=2, predicted_away=1)  # exact 10
        m.home_score, m.away_score = 2, 1
        m.save()

        # Joins AFTER scoring ran, so this member has no MatchScore rows.
        latecomer = join(league).user
        self.assertFalse(latecomer.memberships.get(league=league).scores.exists())

        board = scoring.leaderboard(league)
        by_user = {row["membership"].user_id: row for row in board}
        self.assertEqual(by_user[latecomer.id]["total"], Decimal("0.00"))
        self.assertEqual(by_user[scorer.id]["rank"], 1)
        self.assertEqual(by_user[latecomer.id]["rank"], 2)
        # The scorer leads; the scoreless member never appears above them.
        self.assertEqual(board[0]["membership"].user_id, scorer.id)
        self.assertEqual(board[-1]["membership"].user_id, latecomer.id)


class LiveLeaderboardTests(TestCase):
    """The live view: in-play scores played as if they were the final result."""

    def setUp(self):
        self.comp = make_competition()
        self.league = make_league(self.comp)
        self.a_mem = Membership.objects.get(league=self.league, user=self.league.owner)
        self.b_mem = join(self.league)

    def _go_live(self, match, home, away, status=consts.LiveStatus.LIVE):
        # The sanctioned write path for live state (never save()).
        type(match).objects.filter(pk=match.pk).update(
            live_home_score=home, live_away_score=away, live_status=status,
        )
        match.refresh_from_db()

    def test_no_live_match_mirrors_official(self):
        m = make_match(self.comp)
        Prediction.objects.create(membership=self.a_mem, match=m,
                                  predicted_home=2, predicted_away=1)
        m.home_score, m.away_score = 2, 1
        m.save()

        table, is_live, _live_matches = scoring.live_leaderboard(self.league)
        self.assertFalse(is_live)
        by_user = {row["membership"].id: row for row in table}
        row = by_user[self.a_mem.id]
        self.assertEqual(row["live_total"], row["total"])
        self.assertEqual(row["live_rank"], row["rank"])
        self.assertEqual(row["live_points"], Decimal("0.00"))

    def test_live_match_adds_provisional_points_and_reranks(self):
        # Official: B leads 10-2 from a finished match.
        done = make_match(self.comp)
        Prediction.objects.create(membership=self.b_mem, match=done,
                                  predicted_home=2, predicted_away=1)  # exact 10
        Prediction.objects.create(membership=self.a_mem, match=done,
                                  predicted_home=0, predicted_away=2)  # wrong 2
        done.home_score, done.away_score = 2, 1
        done.save()

        # Live: A predicted the in-play score exactly, B has no prediction.
        playing = make_match(self.comp)
        Prediction.objects.create(membership=self.a_mem, match=playing,
                                  predicted_home=1, predicted_away=0)
        self._go_live(playing, 1, 0)

        table, is_live, _live_matches = scoring.live_leaderboard(self.league)
        self.assertTrue(is_live)
        by_mem = {row["membership"].id: row for row in table}
        a, b = by_mem[self.a_mem.id], by_mem[self.b_mem.id]
        # Official standings are untouched...
        self.assertEqual((a["rank"], b["rank"]), (2, 1))
        self.assertEqual(a["total"], Decimal("2.00"))
        # ...but the live view has A 2+10=12 over B 10+0, flipping the lead.
        self.assertEqual(a["live_points"], Decimal("10.00"))
        self.assertEqual(a["live_total"], Decimal("12.00"))
        self.assertEqual(b["live_points"], Decimal("0.00"))
        self.assertEqual((a["live_rank"], b["live_rank"]), (1, 2))
        # And nothing was persisted for the in-play match.
        self.assertFalse(playing.scores.exists())

    def test_full_time_pending_official_still_counts_as_live(self):
        # Provider says FT but the official result hasn't landed yet: the live
        # view keeps counting it so the board doesn't flicker back.
        playing = make_match(self.comp)
        Prediction.objects.create(membership=self.a_mem, match=playing,
                                  predicted_home=3, predicted_away=0)
        self._go_live(playing, 3, 0, status=consts.LiveStatus.FULL_TIME)

        table, is_live, _live_matches = scoring.live_leaderboard(self.league)
        self.assertTrue(is_live)
        by_mem = {row["membership"].id: row for row in table}
        self.assertEqual(by_mem[self.a_mem.id]["live_points"], Decimal("10.00"))

    def test_finished_match_never_double_counts(self):
        # Once the official result lands, lingering live state must not add on
        # top of the real MatchScore rows.
        m = make_match(self.comp)
        Prediction.objects.create(membership=self.a_mem, match=m,
                                  predicted_home=2, predicted_away=0)
        self._go_live(m, 2, 0, status=consts.LiveStatus.FULL_TIME)
        m.home_score, m.away_score = 2, 0
        m.save()  # official result -> FINISHED + MatchScore

        table, is_live, _live_matches = scoring.live_leaderboard(self.league)
        self.assertFalse(is_live)
        by_mem = {row["membership"].id: row for row in table}
        row = by_mem[self.a_mem.id]
        self.assertEqual(row["total"], Decimal("10.00"))
        self.assertEqual(row["live_total"], Decimal("10.00"))
        self.assertEqual(row["live_points"], Decimal("0.00"))

    def test_live_picks_align_with_live_matches(self):
        # Each row's live_picks must be 1:1 with the returned live_matches, with
        # None for members who didn't predict an in-play match.
        playing = make_match(self.comp)
        Prediction.objects.create(membership=self.a_mem, match=playing,
                                  predicted_home=1, predicted_away=0)
        # b_mem deliberately does not predict this match.
        self._go_live(playing, 1, 0)

        table, is_live, live_matches = scoring.live_leaderboard(self.league)
        self.assertTrue(is_live)
        self.assertEqual([m.id for m in live_matches], [playing.id])

        by_mem = {row["membership"].id: row for row in table}
        self.assertEqual(
            by_mem[self.a_mem.id]["live_picks"],
            [{"match_id": playing.id, "home": 1, "away": 0}],
        )
        self.assertEqual(
            by_mem[self.b_mem.id]["live_picks"],
            [{"match_id": playing.id, "home": None, "away": None}],
        )
