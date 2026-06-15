"""Tests for the matchday recap (predictions/recap.py + the API endpoint).

Scenario — one league, three members (me/u2/u3), two matchdays:

  Matchday 1 (two group matches A1 2-1, A2 0-0)
    me : A1 2-1 exact (10) · A2 1-0 vs 0-0 participation (2)        -> 12
    u2 : A1 1-0 vs 2-1 diff (7) · A2 0-0 exact (10)                 -> 17  (top)
    u3 : A1 no pick (miss) · A2 2-2 vs 0-0 diff (7)                 ->  7

  Matchday 2 (one match B1 1-0)
    me : B1 1-0 exact (10)   ·  u2 no pick  ·  u3 0-2 participation (2)

  Standings after day 1: u2 17, me 12, u3 7  →  after day 2: me 22, u2 17, u3 9
"""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from predictions import consts, recap
from predictions.models import Match, Membership, Prediction

from .factories import join, make_competition, make_league, make_match, make_team, make_user


class RecapTestCase(APITestCase):
    def setUp(self):
        self.comp = make_competition()
        self.me = make_user(email="me@test.com", display_name="من")
        self.league = make_league(self.comp, owner=self.me, name="رفقا")
        self.u2 = join(self.league, make_user(display_name="علی")).user
        self.u3 = join(self.league, make_user(display_name="رضا")).user

        # Three teams' worth of fixtures across two clearly-distinct days. 09:00Z
        # keeps both day-1 matches inside one calendar day in any sane timezone.
        base = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)
        d1, d2 = base - timedelta(days=3), base - timedelta(days=2)
        self.a1 = make_match(self.comp, kickoff=d1)
        self.a2 = make_match(self.comp, kickoff=d1 + timedelta(hours=1))
        self.b1 = make_match(self.comp, kickoff=d2)

        self._predict(self.me, self.a1, 2, 1)
        self._predict(self.me, self.a2, 1, 0)
        self._predict(self.me, self.b1, 1, 0)
        self._predict(self.u2, self.a1, 1, 0)
        self._predict(self.u2, self.a2, 0, 0)
        self._predict(self.u3, self.a2, 2, 2)
        self._predict(self.u3, self.b1, 0, 2)

        self._finalize(self.a1, 2, 1)
        self._finalize(self.a2, 0, 0)
        self._finalize(self.b1, 1, 0)

        self.dates = recap.available_dates(self.comp)  # [day1, day2] ascending

    def _membership(self, user):
        return Membership.objects.get(league=self.league, user=user)

    def _predict(self, user, match, home, away):
        Prediction.objects.create(
            membership=self._membership(user), match=match,
            predicted_home=home, predicted_away=away,
        )

    def _finalize(self, match, home, away):
        # Save the result (status -> FINISHED) so the signal computes everyone's
        # scores; predictions already exist, so they're picked up.
        match.home_score, match.away_score = home, away
        match.save()

    # -- recap.build_recap ------------------------------------------------- #
    def test_two_matchdays_discovered(self):
        self.assertEqual(len(self.dates), 2)

    def test_personal_day1(self):
        data = recap.build_recap(self.league, self._membership(self.me), self.dates[0])
        me = data["me"]
        self.assertEqual(me["points"], 12)
        self.assertEqual(me["predicted"], 2)
        self.assertEqual(me["hits"][consts.Tier.EXACT], 1)
        self.assertEqual(me["hits"][consts.Tier.PARTICIPATION], 1)
        self.assertEqual(me["best"][0].tier, consts.Tier.EXACT)  # best call = the 2-1
        self.assertFalse(me["is_top_scorer"])  # u2 outscored me

    def test_rank_climb_day2(self):
        data = recap.build_recap(self.league, self._membership(self.me), self.dates[1])
        me = data["me"]
        self.assertEqual(me["rank_before"], 2)  # 2nd after day 1
        self.assertEqual(me["rank_after"], 1)   # 1st after day 2
        self.assertEqual(me["rank_delta"], 1)
        self.assertTrue(me["is_top_scorer"])

    def test_general_top_scorer_day1(self):
        data = recap.build_recap(self.league, self._membership(self.me), self.dates[0])
        top = data["general"]["top_scorer"]
        self.assertEqual(top["membership"].user_id, self.u2.id)
        self.assertEqual(top["points"], 17)
        self.assertEqual(top["ties"], 0)

    def test_general_surprise_is_the_low_hit_match(self):
        # Day 1: A1 called right by everyone who predicted it; A2 the upset.
        data = recap.build_recap(self.league, self._membership(self.me), self.dates[0])
        surprise = data["general"]["surprise"]
        self.assertEqual(surprise["match"].id, self.a2.id)
        self.assertEqual(surprise["predicted_count"], 3)

    def test_general_mover_day2_is_me(self):
        data = recap.build_recap(self.league, self._membership(self.me), self.dates[1])
        mover = data["general"]["mover"]
        self.assertEqual(mover["membership"].user_id, self.me.id)
        self.assertEqual(mover["delta"], 1)

    def test_no_finished_matches_is_empty(self):
        empty_comp = make_competition(name="خالی")
        league = make_league(empty_comp, owner=self.me, name="بی‌بازی")
        data = recap.build_recap(league, self._membership_in(league, self.me), None)
        self.assertIsNone(data["date"])
        self.assertIsNone(data["me"])
        self.assertEqual(data["matches"], [])

    def _membership_in(self, league, user):
        return Membership.objects.get(league=league, user=user)

    # -- the API endpoint -------------------------------------------------- #
    def test_endpoint_defaults_to_latest_day(self):
        client = APIClient()
        client.force_authenticate(user=self.me)
        res = client.get(reverse("api_league_recap", args=[self.league.slug]))
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["date"], self.dates[1])           # latest day
        self.assertEqual(body["me"]["points"], 10.0)            # B1 exact
        self.assertEqual(body["me"]["best_call"]["tier"], consts.Tier.EXACT)
        self.assertEqual(body["general"]["mover"]["is_me"], True)
        self.assertEqual(len(body["matches"]), 1)

    def test_endpoint_date_param_selects_day(self):
        client = APIClient()
        client.force_authenticate(user=self.me)
        res = client.get(
            reverse("api_league_recap", args=[self.league.slug]),
            {"date": self.dates[0]},
        )
        body = res.json()
        self.assertEqual(body["date"], self.dates[0])
        self.assertEqual(len(body["matches"]), 2)
        self.assertEqual(body["general"]["top_scorer"]["name"], "علی")
        self.assertEqual(body["me"]["points"], 12.0)

    def test_endpoint_requires_membership(self):
        outsider = make_user(email="out@test.com")
        client = APIClient()
        client.force_authenticate(user=outsider)
        res = client.get(reverse("api_league_recap", args=[self.league.slug]))
        self.assertEqual(res.status_code, 404)
