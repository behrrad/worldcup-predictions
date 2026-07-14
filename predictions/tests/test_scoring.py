"""
Tests for the scoring engine — the heart of the app.

Tier rules (highest applicable wins), then × stage multiplier:
  exact score ............... points_exact          (default 10)
  right winner + right diff . points_correct_diff   (default 7)
  right winner only ......... points_correct_winner (default 5)
  submitted but wrong ....... points_participation  (default 2)
  no prediction ............. 0
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from predictions import consts, scoring
from predictions.models import (
    BonusPrediction,
    BonusScore,
    MatchScore,
    Membership,
    PlayerCandidate,
    Prediction,
    TournamentOutcome,
)

from .factories import (
    join,
    make_competition,
    make_league,
    make_match,
    make_team,
    make_user,
)


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


class BonusScoringTests(TestCase):
    """Tournament-wide bonus picks: exact-match scoring, and the "who wins our
    league" meta-pick scored against the frozen (match + outright) standings."""

    def setUp(self):
        self.comp = make_competition()
        self.owner = make_user()
        self.league = make_league(
            self.comp, owner=self.owner,
            bonus_lock_at=timezone.now() + timedelta(days=1),
        )
        self.alex = Membership.objects.get(league=self.league, user=self.owner)
        self.champ_team = make_team(self.comp, name="تیم قهرمان")
        self.other_team = make_team(self.comp, name="تیم دیگر")
        # A dummy match to hang MatchScore rows on (stays unfinished, so no signal
        # recompute overwrites the totals we set by hand).
        self.match = make_match(self.comp)

    def _set_match_points(self, membership, pts):
        MatchScore.objects.update_or_create(
            membership=membership, match=self.match,
            defaults={"points": Decimal(pts), "tier": consts.Tier.WINNER},
        )

    def test_champion_pick_exact_match(self):
        rival = join(self.league)
        BonusPrediction.objects.create(
            membership=self.alex, kind=consts.BonusKind.CHAMPION, team=self.champ_team)
        BonusPrediction.objects.create(
            membership=rival, kind=consts.BonusKind.CHAMPION, team=self.other_team)
        TournamentOutcome.objects.create(competition=self.comp, champion=self.champ_team)

        scoring.settle_bonus_scores(self.comp)

        winner = BonusScore.objects.get(membership=self.alex, kind=consts.BonusKind.CHAMPION)
        self.assertTrue(winner.correct)
        self.assertEqual(winner.points, Decimal(consts.DEFAULT_POINTS_CHAMPION))
        loser = BonusScore.objects.get(membership=rival, kind=consts.BonusKind.CHAMPION)
        self.assertFalse(loser.correct)
        self.assertEqual(loser.points, Decimal("0"))

    def test_golden_boot_player_pick(self):
        winner = PlayerCandidate.objects.create(competition=self.comp, name="بازیکن الف")
        PlayerCandidate.objects.create(competition=self.comp, name="بازیکن ب")
        BonusPrediction.objects.create(
            membership=self.alex, kind=consts.BonusKind.GOLDEN_BOOT, player=winner)
        TournamentOutcome.objects.create(competition=self.comp, golden_boot=winner)

        scoring.settle_bonus_scores(self.comp)

        score = BonusScore.objects.get(membership=self.alex, kind=consts.BonusKind.GOLDEN_BOOT)
        self.assertTrue(score.correct)
        self.assertEqual(score.points, Decimal(consts.DEFAULT_POINTS_GOLDEN_BOOT))

    def test_league_winner_leapfrog_and_non_circular(self):
        # Frozen standings from match points: Alex 30 > Brad 20 > Jack 10.
        brad = join(self.league)
        jack = join(self.league)
        self._set_match_points(self.alex, 30)
        self._set_match_points(brad, 20)
        self._set_match_points(jack, 10)
        # Big enough meta-pick to reshuffle the podium.
        self.league.points_league_winner = 25
        self.league.save(update_fields=["points_league_winner"])
        # Picks: Jack -> Alex (the frozen #1), Alex -> Brad, Brad -> Brad.
        kind = consts.BonusKind.LEAGUE_WINNER
        BonusPrediction.objects.create(membership=jack, kind=kind, target_membership=self.alex)
        BonusPrediction.objects.create(membership=self.alex, kind=kind, target_membership=brad)
        BonusPrediction.objects.create(membership=brad, kind=kind, target_membership=brad)

        scoring.settle_bonus_scores(self.comp)

        # The frozen champion is Alex — the meta-pick is excluded from its own
        # target, so Jack's +25 (which vaults him to the top) does NOT retroactively
        # make Jack the champion. That non-circularity is exactly why Jack is right.
        self.assertEqual(scoring._frozen_league_champion_id(self.league), self.alex.id)
        jack_score = BonusScore.objects.get(membership=jack, kind=kind)
        self.assertTrue(jack_score.correct)
        self.assertEqual(jack_score.points, Decimal(25))
        self.assertFalse(BonusScore.objects.get(membership=self.alex, kind=kind).correct)
        self.assertFalse(BonusScore.objects.get(membership=brad, kind=kind).correct)

        # Final leaderboard: Jack leapfrogs to #1 (10 + 25 = 35 > Alex's 30).
        rows = {r["membership"].id: r for r in scoring.leaderboard(self.league)}
        self.assertEqual(rows[jack.id]["total"], Decimal("35.00"))
        self.assertEqual(rows[jack.id]["match_total"], Decimal("10.00"))
        self.assertEqual(rows[jack.id]["bonus_total"], Decimal("25.00"))
        self.assertEqual(rows[jack.id]["rank"], 1)
        self.assertEqual(rows[self.alex.id]["rank"], 2)
        self.assertEqual(rows[brad.id]["rank"], 3)

    def test_self_pick_allowed_and_scored(self):
        brad = join(self.league)
        self._set_match_points(self.alex, 30)
        self._set_match_points(brad, 10)
        BonusPrediction.objects.create(
            membership=self.alex, kind=consts.BonusKind.LEAGUE_WINNER,
            target_membership=self.alex,  # backing yourself
        )
        scoring.settle_bonus_scores(self.comp)
        score = BonusScore.objects.get(
            membership=self.alex, kind=consts.BonusKind.LEAGUE_WINNER)
        self.assertTrue(score.correct)
        self.assertEqual(score.points, Decimal(consts.DEFAULT_POINTS_LEAGUE_WINNER))

    def test_settle_is_idempotent(self):
        BonusPrediction.objects.create(
            membership=self.alex, kind=consts.BonusKind.CHAMPION, team=self.champ_team)
        TournamentOutcome.objects.create(competition=self.comp, champion=self.champ_team)
        scoring.settle_bonus_scores(self.comp)
        scoring.settle_bonus_scores(self.comp)
        self.assertEqual(
            BonusScore.objects.filter(
                membership=self.alex, kind=consts.BonusKind.CHAMPION).count(),
            1,
        )

    def test_bonus_absent_leaves_leaderboard_unchanged(self):
        # No bonus scores settled: total == match_total, ordering as before.
        brad = join(self.league)
        self._set_match_points(self.alex, 15)
        self._set_match_points(brad, 5)
        rows = {r["membership"].id: r for r in scoring.leaderboard(self.league)}
        self.assertEqual(rows[self.alex.id]["total"], Decimal("15.00"))
        self.assertEqual(rows[self.alex.id]["bonus_total"], Decimal("0.00"))
        self.assertEqual(rows[self.alex.id]["rank"], 1)


class FairPredictionPointsTests(TestCase):
    """The site-wide fair scale: default ladder, no stage multiplier."""

    def setUp(self):
        self.comp = make_competition()

    def _finished(self, home, away, stage=consts.Stage.GROUP, penalty_winner=""):
        m = make_match(self.comp, stage=stage)
        m.home_score, m.away_score = home, away
        m.penalty_winner = penalty_winner
        m.save()
        return m

    def _pred(self, home, away, advancer=consts.Advancer.NONE):
        league = make_league(self.comp)
        member = Membership.objects.get(league=league)
        return Prediction.objects.create(
            membership=member, match=make_match(self.comp),
            predicted_home=home, predicted_away=away, predicted_advancer=advancer,
        )

    def test_group_ladder(self):
        m = self._finished(2, 1)
        for (h, a), points, tier in (
            ((2, 1), 10, consts.Tier.EXACT),
            ((3, 2), 7, consts.Tier.DIFF),
            ((3, 1), 5, consts.Tier.WINNER),
            ((0, 0), 2, consts.Tier.PARTICIPATION),
        ):
            pts, t = scoring.fair_prediction_points(m, self._pred(h, a))
            self.assertEqual((pts, t), (Decimal(points), tier))

    def test_no_prediction_is_zero(self):
        m = self._finished(2, 1)
        self.assertEqual(
            scoring.fair_prediction_points(m, None),
            (Decimal("0.00"), consts.Tier.NONE),
        )

    def test_knockout_has_no_multiplier(self):
        # The whole point of the fair scale: an exact knockout pick is 10, not 15.
        m = self._finished(2, 1, stage=consts.Stage.ROUND_OF_16)
        pts, tier = scoring.fair_prediction_points(m, self._pred(2, 1))
        self.assertEqual((pts, tier), (Decimal("10.00"), consts.Tier.EXACT))

    def test_penalty_shootout_rules_apply_unmultiplied(self):
        # 1-1 at 120', home advances on pens: exact draw + right advancer = 10.
        m = self._finished(
            1, 1, stage=consts.Stage.QUARTER, penalty_winner=consts.Advancer.HOME,
        )
        pts, tier = scoring.fair_prediction_points(
            m, self._pred(1, 1, advancer=consts.Advancer.HOME),
        )
        self.assertEqual((pts, tier), (Decimal("10.00"), consts.Tier.EXACT))
        # A non-draw pick on a shootout match is plain participation (2).
        pts, tier = scoring.fair_prediction_points(m, self._pred(2, 1))
        self.assertEqual((pts, tier), (Decimal("2.00"), consts.Tier.PARTICIPATION))


class GlobalScoreboardTests(TestCase):
    """The cross-league board: fair ×1 totals, player averages, league averages."""

    def setUp(self):
        self.comp = make_competition()
        # Two leagues with wildly different configs — the fair board must not care.
        self.league_a = make_league(self.comp, name="لیگ الف")
        self.league_b = make_league(
            self.comp, name="لیگ ب", points_exact=50, multiplier_r16=Decimal("3.0"),
        )
        self.u1 = make_user()  # in both leagues
        self.u2 = make_user()  # only in league A
        self.a1 = join(self.league_a, self.u1)
        self.b1 = join(self.league_b, self.u1)
        self.a2 = join(self.league_a, self.u2)
        self.b3 = join(self.league_b)  # u3: member, never predicts
        self.u3 = self.b3.user

        self.m1 = make_match(self.comp)                                  # group
        self.m2 = make_match(self.comp, stage=consts.Stage.ROUND_OF_16)  # knockout

    def _finish(self, match, home, away):
        match.home_score, match.away_score = home, away
        match.save()

    def _board(self):
        board = scoring.global_scoreboard(self.comp)
        players = {r["user"].id: r for r in board["players"]}
        leagues = {r["league"].id: r for r in board["leagues"]}
        return board, players, leagues

    def test_fair_totals_ignore_league_config_and_dedupe_per_user(self):
        # u1 predicts m1 in league A first (exact), then differently in league B
        # — only the earlier pick counts on the player board.
        Prediction.objects.create(membership=self.a1, match=self.m1,
                                  predicted_home=2, predicted_away=1)
        Prediction.objects.create(membership=self.b1, match=self.m1,
                                  predicted_home=0, predicted_away=0)
        # u1's m2 pick exists only in league B (points_exact=50, r16 ×3): the
        # fair board must still award the default 10 with no multiplier.
        Prediction.objects.create(membership=self.b1, match=self.m2,
                                  predicted_home=3, predicted_away=0)
        # u2 gets the winner only on m1 (5).
        Prediction.objects.create(membership=self.a2, match=self.m1,
                                  predicted_home=3, predicted_away=1)
        self._finish(self.m1, 2, 1)
        self._finish(self.m2, 3, 0)

        _, players, _ = self._board()
        self.assertEqual(players[self.u1.id]["total"], Decimal("20.00"))  # 10 + 10
        self.assertEqual(players[self.u1.id]["played"], 2)
        self.assertEqual(players[self.u1.id]["exact_count"], 2)
        self.assertEqual(players[self.u2.id]["total"], Decimal("5.00"))
        # Members who never predicted still appear, at zero.
        self.assertEqual(players[self.u3.id]["total"], Decimal("0.00"))
        self.assertEqual(players[self.u1.id]["rank"], 1)
        self.assertEqual(players[self.u2.id]["rank"], 2)

    def test_average_view_gated_at_half_of_finished(self):
        # 2 finished matches -> the bar is 1 predicted game.
        Prediction.objects.create(membership=self.a1, match=self.m1,
                                  predicted_home=2, predicted_away=1)  # exact 10
        Prediction.objects.create(membership=self.b1, match=self.m2,
                                  predicted_home=0, predicted_away=2)  # wrong 2
        Prediction.objects.create(membership=self.a2, match=self.m1,
                                  predicted_home=3, predicted_away=1)  # winner 5
        self._finish(self.m1, 2, 1)
        self._finish(self.m2, 3, 0)

        _, players, _ = self._board()
        self.assertEqual(players[self.u1.id]["avg_points"], Decimal("6.0000"))  # 12/2
        self.assertEqual(players[self.u2.id]["avg_points"], Decimal("5.0000"))
        self.assertTrue(players[self.u1.id]["eligible_for_avg"])
        self.assertTrue(players[self.u2.id]["eligible_for_avg"])
        self.assertFalse(players[self.u3.id]["eligible_for_avg"])
        self.assertEqual(players[self.u1.id]["avg_rank"], 1)
        self.assertEqual(players[self.u2.id]["avg_rank"], 2)
        self.assertIsNone(players[self.u3.id]["avg_rank"])

    def test_league_average_is_mean_of_eligible_member_averages(self):
        # League A: u1 avg 10 (1 predicted game), u2 avg 5 -> league avg 7.5.
        # The non-predicting owner is simply not part of the mean.
        Prediction.objects.create(membership=self.a1, match=self.m1,
                                  predicted_home=2, predicted_away=1)
        Prediction.objects.create(membership=self.a2, match=self.m1,
                                  predicted_home=3, predicted_away=1)
        # League B: u1's membership predicted both games (2 + 10 = 12, avg 6).
        Prediction.objects.create(membership=self.b1, match=self.m1,
                                  predicted_home=0, predicted_away=0)
        Prediction.objects.create(membership=self.b1, match=self.m2,
                                  predicted_home=3, predicted_away=0)
        self._finish(self.m1, 2, 1)
        self._finish(self.m2, 3, 0)

        _, _, leagues = self._board()
        row_a = leagues[self.league_a.id]
        row_b = leagues[self.league_b.id]
        self.assertEqual(row_a["avg_points"], Decimal("7.5000"))
        self.assertEqual(row_a["eligible_count"], 2)
        self.assertEqual(row_a["member_count"], 3)  # owner + u1 + u2
        self.assertEqual(row_b["avg_points"], Decimal("6.0000"))
        self.assertEqual(row_a["rank"], 1)
        self.assertEqual(row_b["rank"], 2)

    def test_league_without_eligible_members_is_unranked(self):
        Prediction.objects.create(membership=self.a1, match=self.m1,
                                  predicted_home=2, predicted_away=1)
        self._finish(self.m1, 2, 1)
        self._finish(self.m2, 3, 0)

        board, _, leagues = self._board()
        # Nobody in league B predicted anything -> no average, no rank, last.
        self.assertIsNone(leagues[self.league_b.id]["avg_points"])
        self.assertIsNone(leagues[self.league_b.id]["rank"])
        self.assertEqual(board["leagues"][-1]["league"].id, self.league_b.id)

    def test_no_finished_matches_means_nobody_eligible(self):
        Prediction.objects.create(membership=self.a1, match=self.m1,
                                  predicted_home=2, predicted_away=1)
        board, players, leagues = self._board()
        self.assertEqual(board["finished_count"], 0)
        self.assertFalse(players[self.u1.id]["eligible_for_avg"])
        self.assertIsNone(leagues[self.league_a.id]["avg_points"])

    def test_voided_match_excluded(self):
        Prediction.objects.create(membership=self.a1, match=self.m1,
                                  predicted_home=2, predicted_away=1)
        self.m1.count_for_scoring = False
        self._finish(self.m1, 2, 1)

        board, players, _ = self._board()
        self.assertEqual(board["finished_count"], 0)
        self.assertEqual(players[self.u1.id]["total"], Decimal("0.00"))
        self.assertEqual(players[self.u1.id]["played"], 0)
