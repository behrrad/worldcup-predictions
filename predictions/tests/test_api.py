from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.test import APITestCase

from predictions import consts
from predictions.models import League, Membership, Prediction

from .factories import join, make_competition, make_league, make_match, make_user


class AuthRequiredTests(APITestCase):
    def test_endpoints_require_auth(self):
        client = APIClient()
        self.assertEqual(client.get(reverse("api_me")).status_code, 401)
        self.assertEqual(client.get(reverse("api_leagues")).status_code, 401)


class AuthedTestCase(APITestCase):
    def setUp(self):
        self.user = make_user(email="me@test.com", display_name="من")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.comp = make_competition()


class MeAndCompetitionsTests(AuthedTestCase):
    def test_me(self):
        res = self.client.get(reverse("api_me"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["email"], "me@test.com")

    def test_competitions(self):
        res = self.client.get(reverse("api_competitions"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 1)


class LeagueCrudTests(AuthedTestCase):
    def test_create_league_makes_owner_membership(self):
        res = self.client.post(reverse("api_leagues"), {
            "name": "لیگ من", "competition_id": self.comp.id, "description": "",
        }, format="json")
        self.assertEqual(res.status_code, 201)
        slug = res.json()["slug"]
        league = League.objects.get(slug=slug)
        self.assertEqual(league.owner, self.user)
        m = Membership.objects.get(league=league, user=self.user)
        self.assertEqual(m.role, consts.Role.OWNER)
        self.assertTrue(res.json()["is_owner"])
        self.assertIsNotNone(res.json()["invite_code"])

    def test_create_league_requires_name(self):
        res = self.client.post(reverse("api_leagues"), {
            "name": "", "competition_id": self.comp.id,
        }, format="json")
        self.assertEqual(res.status_code, 400)

    def test_list_my_leagues(self):
        make_league(self.comp, owner=self.user, name="یکی")
        res = self.client.get(reverse("api_leagues"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 1)


class JoinLeagueTests(AuthedTestCase):
    def test_join_with_code(self):
        league = make_league(self.comp, name="گروه")
        res = self.client.post(reverse("api_join_league"),
                               {"invite_code": league.invite_code}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["created"])
        self.assertTrue(Membership.objects.filter(league=league, user=self.user).exists())

    def test_join_invalid_code(self):
        res = self.client.post(reverse("api_join_league"),
                               {"invite_code": "NOPE9999"}, format="json")
        self.assertEqual(res.status_code, 404)

    def test_join_twice_is_idempotent(self):
        league = make_league(self.comp)
        self.client.post(reverse("api_join_league"),
                         {"invite_code": league.invite_code}, format="json")
        res = self.client.post(reverse("api_join_league"),
                               {"invite_code": league.invite_code}, format="json")
        self.assertFalse(res.json()["created"])


class LeagueDetailTests(AuthedTestCase):
    def test_owner_sees_invite_code(self):
        league = make_league(self.comp, owner=self.user)
        res = self.client.get(reverse("api_league_detail", args=[league.slug]))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["invite_code"], league.invite_code)

    def test_member_does_not_see_invite_code(self):
        league = make_league(self.comp)  # owned by someone else
        join(league, user=self.user)
        res = self.client.get(reverse("api_league_detail", args=[league.slug]))
        self.assertIsNone(res.json()["invite_code"])

    def test_non_member_gets_404(self):
        league = make_league(self.comp)  # not joined
        res = self.client.get(reverse("api_league_detail", args=[league.slug]))
        self.assertEqual(res.status_code, 404)


class SubmitPredictionsTests(AuthedTestCase):
    def setUp(self):
        super().setUp()
        self.league = make_league(self.comp, owner=self.user)
        self.now = timezone.now()

    def test_saves_open_match(self):
        m = make_match(self.comp, kickoff=self.now + timedelta(hours=2))
        res = self.client.post(
            reverse("api_submit_predictions", args=[self.league.slug]),
            {"predictions": [{"match_id": m.id, "home": 2, "away": 1}]},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["saved"], 1)
        p = Prediction.objects.get(match=m)
        self.assertEqual((p.predicted_home, p.predicted_away), (2, 1))

    def test_ignores_locked_match(self):
        # kickoff in 10 min, lock 30 -> closed
        m = make_match(self.comp, kickoff=self.now + timedelta(minutes=10))
        res = self.client.post(
            reverse("api_submit_predictions", args=[self.league.slug]),
            {"predictions": [{"match_id": m.id, "home": 1, "away": 0}]},
            format="json",
        )
        self.assertEqual(res.json()["saved"], 0)
        self.assertFalse(Prediction.objects.filter(match=m).exists())

    def test_updates_existing_prediction(self):
        m = make_match(self.comp, kickoff=self.now + timedelta(hours=2))
        url = reverse("api_submit_predictions", args=[self.league.slug])
        self.client.post(url, {"predictions": [{"match_id": m.id, "home": 1, "away": 1}]}, format="json")
        self.client.post(url, {"predictions": [{"match_id": m.id, "home": 3, "away": 0}]}, format="json")
        p = Prediction.objects.get(match=m)
        self.assertEqual((p.predicted_home, p.predicted_away), (3, 0))
        self.assertEqual(Prediction.objects.filter(match=m).count(), 1)

    def test_rejects_negative_scores(self):
        m = make_match(self.comp, kickoff=self.now + timedelta(hours=2))
        res = self.client.post(
            reverse("api_submit_predictions", args=[self.league.slug]),
            {"predictions": [{"match_id": m.id, "home": -1, "away": 0}]},
            format="json",
        )
        self.assertEqual(res.json()["saved"], 0)


class LeaderboardApiTests(AuthedTestCase):
    def test_leaderboard_reflects_scores(self):
        league = make_league(self.comp, owner=self.user)
        mem = Membership.objects.get(league=league, user=self.user)
        m = make_match(self.comp)
        Prediction.objects.create(membership=mem, match=m, predicted_home=2, predicted_away=1)
        m.home_score, m.away_score = 2, 1
        m.save()
        res = self.client.get(reverse("api_leaderboard", args=[league.slug]))
        self.assertEqual(res.status_code, 200)
        row = res.json()[0]
        self.assertEqual(row["total"], 10.0)
        self.assertTrue(row["is_me"])


class MatchDetailRevealTests(AuthedTestCase):
    def setUp(self):
        super().setUp()
        self.league = make_league(self.comp, owner=self.user)
        self.mem = Membership.objects.get(league=self.league, user=self.user)
        self.now = timezone.now()

    def test_hidden_before_lock(self):
        m = make_match(self.comp, kickoff=self.now + timedelta(hours=2))
        Prediction.objects.create(membership=self.mem, match=m, predicted_home=1, predicted_away=0)
        res = self.client.get(reverse("api_match_detail", args=[self.league.slug, m.id]))
        self.assertFalse(res.json()["revealed"])
        self.assertEqual(res.json()["predictions"], [])

    def test_revealed_after_lock(self):
        m = make_match(self.comp, kickoff=self.now - timedelta(minutes=5))
        Prediction.objects.create(membership=self.mem, match=m, predicted_home=1, predicted_away=0)
        res = self.client.get(reverse("api_match_detail", args=[self.league.slug, m.id]))
        self.assertTrue(res.json()["revealed"])
        self.assertEqual(len(res.json()["predictions"]), 1)
