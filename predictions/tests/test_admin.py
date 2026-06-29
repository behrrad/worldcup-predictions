from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from predictions import consts
from predictions.models import MatchScore, Prediction

from .factories import make_competition, make_league, make_match, make_team, make_user


class AdminResultsTests(APITestCase):
    def setUp(self):
        self.admin = make_user(email="admin@test.com")
        self.admin.is_staff = True
        self.admin.save()
        self.normal = make_user(email="normal@test.com")

        self.comp = make_competition()
        self.home = make_team(self.comp, name="ایران")
        self.away = make_team(self.comp, name="آمریکا")
        self.match = make_match(
            self.comp, home=self.home, away=self.away,
            kickoff=timezone.now() - timedelta(hours=3),
        )
        # A member who predicted exactly, so a written result yields points.
        self.league = make_league(self.comp)
        self.member = self.league.memberships.first()
        Prediction.objects.create(
            membership=self.member, match=self.match,
            predicted_home=2, predicted_away=1,
        )
        self.client = APIClient()

    def test_me_reports_admin_flag(self):
        self.client.force_authenticate(self.admin)
        self.assertTrue(self.client.get(reverse("api_me")).json()["is_admin"])
        self.client.force_authenticate(self.normal)
        self.assertFalse(self.client.get(reverse("api_me")).json()["is_admin"])

    def test_non_admin_is_forbidden(self):
        self.client.force_authenticate(self.normal)
        self.assertEqual(self.client.get(reverse("api_admin_matches")).status_code, 403)
        res = self.client.post(
            reverse("api_admin_set_result", args=[self.match.id]),
            {"home_score": 2, "away_score": 1}, format="json")
        self.assertEqual(res.status_code, 403)

    def test_admin_lists_matches(self):
        self.client.force_authenticate(self.admin)
        res = self.client.get(reverse("api_admin_matches"))
        self.assertEqual(res.status_code, 200)
        self.assertIn(self.match.id, [m["id"] for m in res.json()])

    def test_admin_sets_result_and_scoreboard_recomputes(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            reverse("api_admin_set_result", args=[self.match.id]),
            {"home_score": 2, "away_score": 1}, format="json")
        self.assertEqual(res.status_code, 200)

        self.match.refresh_from_db()
        self.assertEqual((self.match.home_score, self.match.away_score), (2, 1))
        self.assertEqual(self.match.status, consts.MatchStatus.FINISHED)

        # The post_save signal recomputed the member's score for this match.
        score = MatchScore.objects.get(membership=self.member, match=self.match)
        self.assertEqual(score.tier, consts.Tier.EXACT)
        self.assertGreater(float(score.points), 0)

    def test_admin_clears_result(self):
        self.match.home_score, self.match.away_score = 1, 0
        self.match.save()
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            reverse("api_admin_set_result", args=[self.match.id]),
            {"home_score": None, "away_score": None}, format="json")
        self.assertEqual(res.status_code, 200)
        self.match.refresh_from_db()
        self.assertIsNone(self.match.home_score)
        self.assertEqual(self.match.status, consts.MatchStatus.SCHEDULED)

    def test_invalid_score_rejected(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            reverse("api_admin_set_result", args=[self.match.id]),
            {"home_score": -1, "away_score": 2}, format="json")
        self.assertEqual(res.status_code, 400)
        self.match.refresh_from_db()
        self.assertIsNone(self.match.home_score)  # unchanged

    def test_admin_sets_penalty_winner_on_knockout_draw(self):
        self.match.stage = consts.Stage.SEMI
        self.match.save()
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            reverse("api_admin_set_result", args=[self.match.id]),
            {"home_score": 1, "away_score": 1, "penalty_winner": "AWAY"},
            format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["penalty_winner"], "AWAY")
        self.match.refresh_from_db()
        self.assertEqual(self.match.penalty_winner, consts.Advancer.AWAY)

    def test_penalty_winner_ignored_on_decisive_knockout(self):
        self.match.stage = consts.Stage.SEMI
        self.match.save()
        self.client.force_authenticate(self.admin)
        self.client.post(
            reverse("api_admin_set_result", args=[self.match.id]),
            {"home_score": 2, "away_score": 1, "penalty_winner": "HOME"},
            format="json")
        self.match.refresh_from_db()
        self.assertEqual(self.match.penalty_winner, consts.Advancer.NONE)

    def test_penalty_winner_ignored_on_group_draw(self):
        # self.match is a group match by default — a shootout makes no sense.
        self.client.force_authenticate(self.admin)
        self.client.post(
            reverse("api_admin_set_result", args=[self.match.id]),
            {"home_score": 1, "away_score": 1, "penalty_winner": "HOME"},
            format="json")
        self.match.refresh_from_db()
        self.assertEqual(self.match.penalty_winner, consts.Advancer.NONE)

    def test_clearing_result_clears_penalty_winner(self):
        self.match.stage = consts.Stage.SEMI
        self.match.home_score, self.match.away_score = 1, 1
        self.match.penalty_winner = consts.Advancer.HOME
        self.match.save()
        self.client.force_authenticate(self.admin)
        self.client.post(
            reverse("api_admin_set_result", args=[self.match.id]),
            {"home_score": None, "away_score": None}, format="json")
        self.match.refresh_from_db()
        self.assertEqual(self.match.penalty_winner, consts.Advancer.NONE)
