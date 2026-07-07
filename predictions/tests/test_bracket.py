"""
Tests for the knockout bracket auto-advance (predictions/bracket.py).

The advancer reads the "Match N Winner/Loser" wiring and, once a feeding match
is finished, drops the advancing/eliminated side into the slot it feeds — using
queryset.update() so it never scores or disturbs predictions.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from predictions import bracket, consts
from predictions import seed_data as sd
from predictions.models import Match, MatchScore, Membership, Prediction

from .factories import join, make_competition, make_league, make_team


def _match(comp, number, stage, home=None, away=None, hs=None, as_=None, pen=""):
    return Match.objects.create(
        competition=comp, match_number=number, stage=stage,
        home_team=home, away_team=away, home_score=hs, away_score=as_,
        penalty_winner=pen, kickoff=timezone.now() + timedelta(days=1),
    )


class AdvanceBracketTests(TestCase):
    def setUp(self):
        self.comp = make_competition()
        self.a = make_team(self.comp, name="آ")
        self.b = make_team(self.comp, name="ب")

    def test_winner_fills_next_slot(self):
        src = _match(self.comp, 73, consts.Stage.ROUND_OF_32, self.a, self.b, hs=2, as_=0)
        target = _match(self.comp, 90, consts.Stage.ROUND_OF_16)  # team-less
        edges = {90: {consts.SIDE_HOME: (73, consts.BRACKET_WINNER),
                      consts.SIDE_AWAY: None}}

        filled = bracket.advance_bracket(self.comp, edges=edges)
        target.refresh_from_db()
        self.assertEqual(filled, 1)
        self.assertEqual(target.home_team_id, self.a.id)  # A won 2-0
        self.assertIsNone(target.away_team_id)            # away slot has no ref

    def test_penalty_winner_advances(self):
        # Level at 120', away wins the shootout -> away advances.
        _match(self.comp, 74, consts.Stage.ROUND_OF_32, self.a, self.b,
               hs=1, as_=1, pen=consts.Advancer.AWAY)
        target = _match(self.comp, 89, consts.Stage.ROUND_OF_16)
        edges = {89: {consts.SIDE_HOME: (74, consts.BRACKET_WINNER),
                      consts.SIDE_AWAY: None}}

        bracket.advance_bracket(self.comp, edges=edges)
        target.refresh_from_db()
        self.assertEqual(target.home_team_id, self.b.id)  # B won on penalties

    def test_loser_fills_third_place_slot(self):
        _match(self.comp, 101, consts.Stage.SEMI, self.a, self.b, hs=3, as_=1)
        target = _match(self.comp, 103, consts.Stage.THIRD_PLACE)
        edges = {103: {consts.SIDE_HOME: (101, consts.BRACKET_LOSER),
                       consts.SIDE_AWAY: None}}

        bracket.advance_bracket(self.comp, edges=edges)
        target.refresh_from_db()
        self.assertEqual(target.home_team_id, self.b.id)  # B lost the semi

    def test_unfinished_source_is_skipped(self):
        _match(self.comp, 73, consts.Stage.ROUND_OF_32, self.a, self.b)  # no result
        target = _match(self.comp, 90, consts.Stage.ROUND_OF_16)
        edges = {90: {consts.SIDE_HOME: (73, consts.BRACKET_WINNER),
                      consts.SIDE_AWAY: None}}

        self.assertEqual(bracket.advance_bracket(self.comp, edges=edges), 0)
        target.refresh_from_db()
        self.assertIsNone(target.home_team_id)

    def test_partial_fill_waits_for_the_other_side(self):
        c = make_team(self.comp, name="ج")
        d = make_team(self.comp, name="د")
        _match(self.comp, 73, consts.Stage.ROUND_OF_32, self.a, self.b, hs=2, as_=1)
        _match(self.comp, 75, consts.Stage.ROUND_OF_32, c, d)  # not finished
        target = _match(self.comp, 90, consts.Stage.ROUND_OF_16)
        edges = {90: {consts.SIDE_HOME: (73, consts.BRACKET_WINNER),
                      consts.SIDE_AWAY: (75, consts.BRACKET_WINNER)}}

        filled = bracket.advance_bracket(self.comp, edges=edges)
        target.refresh_from_db()
        self.assertEqual(filled, 1)
        self.assertEqual(target.home_team_id, self.a.id)
        self.assertIsNone(target.away_team_id)  # match 75 still undecided

    def test_idempotent_and_never_overwrites(self):
        src = _match(self.comp, 73, consts.Stage.ROUND_OF_32, self.a, self.b, hs=2, as_=0)
        # Home slot pre-filled by hand with the "wrong" team; must be left alone.
        target = _match(self.comp, 90, consts.Stage.ROUND_OF_16, home=self.b)
        edges = {90: {consts.SIDE_HOME: (73, consts.BRACKET_WINNER),
                      consts.SIDE_AWAY: None}}

        self.assertEqual(bracket.advance_bracket(self.comp, edges=edges), 0)
        target.refresh_from_db()
        self.assertEqual(target.home_team_id, self.b.id)  # untouched

    def test_update_does_not_score_or_wipe_predictions(self):
        _match(self.comp, 73, consts.Stage.ROUND_OF_32, self.a, self.b, hs=2, as_=0)
        target = _match(self.comp, 90, consts.Stage.ROUND_OF_16)
        league = make_league(self.comp)
        member = Membership.objects.get(league=league)
        # A stray prediction already sitting on the fixture must survive.
        Prediction.objects.create(membership=member, match=target,
                                  predicted_home=1, predicted_away=0)
        edges = {90: {consts.SIDE_HOME: (73, consts.BRACKET_WINNER),
                      consts.SIDE_AWAY: None}}

        bracket.advance_bracket(self.comp, edges=edges)
        target.refresh_from_db()
        self.assertEqual(target.home_team_id, self.a.id)
        self.assertEqual(target.status, consts.MatchStatus.SCHEDULED)  # not finalized
        self.assertFalse(MatchScore.objects.filter(match=target).exists())
        self.assertTrue(Prediction.objects.filter(match=target, membership=member).exists())

    def test_cascades_round_by_round(self):
        r32 = _match(self.comp, 73, consts.Stage.ROUND_OF_32, self.a, self.b, hs=2, as_=0)
        r16 = _match(self.comp, 90, consts.Stage.ROUND_OF_16)
        qf = _match(self.comp, 97, consts.Stage.QUARTER)
        edges = {
            90: {consts.SIDE_HOME: (73, consts.BRACKET_WINNER), consts.SIDE_AWAY: None},
            97: {consts.SIDE_HOME: (90, consts.BRACKET_WINNER), consts.SIDE_AWAY: None},
        }
        # First pass: R16 fills from the finished R32; QF can't yet (R16 unplayed).
        bracket.advance_bracket(self.comp, edges=edges)
        r16.refresh_from_db(); qf.refresh_from_db()
        self.assertEqual(r16.home_team_id, self.a.id)
        self.assertIsNone(qf.home_team_id)
        # Play the R16, advance again: QF now fills.
        r16.away_team = self.b; r16.home_score, r16.away_score = 3, 1; r16.save()
        bracket.advance_bracket(self.comp, edges=edges)
        qf.refresh_from_db()
        self.assertEqual(qf.home_team_id, self.a.id)  # A won the R16 3-1

    def test_non_wc_competition_is_a_noop_without_explicit_edges(self):
        # No edges passed + not the WC slug -> gated off (won't misapply WC wiring).
        _match(self.comp, 73, consts.Stage.ROUND_OF_32, self.a, self.b, hs=2, as_=0)
        _match(self.comp, 90, consts.Stage.ROUND_OF_16)
        self.assertNotEqual(self.comp.slug, sd.WC2026_SLUG)
        self.assertEqual(bracket.advance_bracket(self.comp), 0)


class BracketEdgesFromJsonTests(TestCase):
    """The wiring parsed from the real schedule JSON matches the FIFA bracket."""

    def test_real_bracket_edges(self):
        edges = bracket.load_bracket_edges()
        W = consts.BRACKET_WINNER
        L = consts.BRACKET_LOSER
        # A few representative R16/QF/SF/Final/3rd-place slots.
        self.assertEqual(edges[89], {consts.SIDE_HOME: (74, W), consts.SIDE_AWAY: (77, W)})
        self.assertEqual(edges[90], {consts.SIDE_HOME: (73, W), consts.SIDE_AWAY: (75, W)})
        self.assertEqual(edges[97], {consts.SIDE_HOME: (89, W), consts.SIDE_AWAY: (90, W)})
        self.assertEqual(edges[101], {consts.SIDE_HOME: (97, W), consts.SIDE_AWAY: (98, W)})
        self.assertEqual(edges[103], {consts.SIDE_HOME: (101, L), consts.SIDE_AWAY: (102, L)})
        self.assertEqual(edges[104], {consts.SIDE_HOME: (101, W), consts.SIDE_AWAY: (102, W)})
        # Group-stage/R32 fixtures name teams, not matches — no edges.
        self.assertNotIn(73, edges)
        self.assertNotIn(1, edges)
