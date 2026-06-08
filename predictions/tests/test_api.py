import shutil
import tempfile
from datetime import timedelta
from io import BytesIO
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient
from rest_framework.test import APITestCase

from accounts import consts as acc_consts
from predictions import consts
from predictions.models import League, Match, Membership, Prediction
from predictions.throttles import JoinLeagueThrottle

from .factories import (
    join,
    make_competition,
    make_league,
    make_match,
    make_team,
    make_user,
)


def _png_upload(name="avatar.png", color="red"):
    """A small, real PNG wrapped as a multipart upload."""
    buf = BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, format="PNG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/png")


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
        # Before lock the predictor is listed by name, but the score is hidden.
        m = make_match(self.comp, kickoff=self.now + timedelta(hours=2))
        Prediction.objects.create(membership=self.mem, match=m, predicted_home=1, predicted_away=0)
        body = self.client.get(
            reverse("api_match_detail", args=[self.league.slug, m.id])
        ).json()
        self.assertFalse(body["revealed"])
        self.assertEqual(len(body["predictions"]), 1)
        row = body["predictions"][0]
        self.assertTrue(row["is_me"])
        self.assertIsNone(row["home"])
        self.assertIsNone(row["away"])
        self.assertIsNone(row["points"])

    def test_revealed_after_lock(self):
        m = make_match(self.comp, kickoff=self.now - timedelta(minutes=5))
        Prediction.objects.create(membership=self.mem, match=m, predicted_home=1, predicted_away=0)
        body = self.client.get(
            reverse("api_match_detail", args=[self.league.slug, m.id])
        ).json()
        self.assertTrue(body["revealed"])
        self.assertEqual(len(body["predictions"]), 1)
        self.assertEqual(body["predictions"][0]["home"], 1)
        self.assertEqual(body["predictions"][0]["away"], 0)

    def test_other_members_names_shown_scores_hidden_before_lock(self):
        # A second member's prediction: name visible, pick hidden until lock.
        other = join(self.league)
        m = make_match(self.comp, kickoff=self.now + timedelta(hours=2))
        Prediction.objects.create(membership=other, match=m, predicted_home=3, predicted_away=2)
        body = self.client.get(
            reverse("api_match_detail", args=[self.league.slug, m.id])
        ).json()
        self.assertFalse(body["revealed"])
        self.assertEqual(body["member_count"], 2)
        row = next(r for r in body["predictions"] if r["name"] == other.user.public_name)
        self.assertFalse(row["is_me"])
        self.assertIsNone(row["home"])  # score stays hidden
        self.assertIsNone(row["away"])


class ThrottleTests(AuthedTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()  # throttle history lives in the cache; isolate this test

    def test_join_league_is_throttled(self):
        # DRF binds SimpleRateThrottle.THROTTLE_RATES at import time, so
        # override_settings can't reach it — patch the rate dict directly.
        league = make_league(self.comp)  # owned by someone else; self.user joins
        payload = {"invite_code": league.invite_code}
        with mock.patch.dict(JoinLeagueThrottle.THROTTLE_RATES,
                             {consts.THROTTLE_SCOPE_JOIN: "1/min"}):
            first = self.client.post(reverse("api_join_league"), payload, format="json")
            second = self.client.post(reverse("api_join_league"), payload, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)


class LeagueMatchesApiTests(AuthedTestCase):
    def setUp(self):
        super().setUp()
        self.league = make_league(self.comp, owner=self.user)

    def test_venue_and_bracket_labels_in_payload(self):
        # A group match with real teams + a venue.
        group = make_match(self.comp, kickoff=timezone.now() + timedelta(days=1),
                           venue="Estadio Azteca")
        # A knockout match with no teams yet, carrying English bracket labels.
        ko = Match.objects.create(
            competition=self.comp, match_number=73, stage=consts.Stage.ROUND_OF_32,
            home_team=None, away_team=None, venue="SoFi Stadium",
            home_label="Group A Winner", away_label="Match 80 Winner",
            kickoff=timezone.now() + timedelta(days=20),
        )
        res = self.client.get(reverse("api_league_matches", args=[self.league.slug]))
        self.assertEqual(res.status_code, 200)
        by_id = {m["id"]: m for m in res.json()}

        g = by_id[group.id]
        self.assertEqual(g["venue"], "Estadio Azteca")
        self.assertIsNone(g["home_label"])  # real teams -> no placeholder

        k = by_id[ko.id]
        self.assertEqual(k["venue"], "SoFi Stadium")
        self.assertIsNone(k["home_team"])
        self.assertEqual(k["home_label"], "صدرنشین گروه A")
        self.assertEqual(k["away_label"], "برندهٔ بازی ۸۰")

    def test_teamless_match_without_label_falls_back_to_unknown(self):
        ko = Match.objects.create(
            competition=self.comp, match_number=200, stage=consts.Stage.ROUND_OF_32,
            home_team=None, away_team=None, kickoff=timezone.now() + timedelta(days=20),
        )
        res = self.client.get(reverse("api_league_matches", args=[self.league.slug]))
        k = next(m for m in res.json() if m["id"] == ko.id)
        self.assertEqual(k["home_label"], consts.BRACKET_UNKNOWN)
        self.assertEqual(k["away_label"], consts.BRACKET_UNKNOWN)


class ProfileMeTests(AuthedTestCase):
    def test_me_returns_full_profile(self):
        body = self.client.get(reverse("api_me")).json()
        self.assertEqual(body["email"], "me@test.com")
        for key in ("id", "display_name", "public_name", "avatar", "bio",
                    "location", "social_handle", "favorite_team", "joined_at"):
            self.assertIn(key, body)
        self.assertIsNone(body["avatar"])
        self.assertIsNone(body["favorite_team"])

    def test_patch_updates_text_fields(self):
        res = self.client.patch(reverse("api_me"), {
            "display_name": "  علی  ", "bio": "سلام", "location": "تهران",
            "social_handle": "@ali",
        }, format="json")
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, "علی")  # trimmed
        self.assertEqual(self.user.bio, "سلام")
        self.assertEqual(self.user.location, "تهران")
        self.assertEqual(self.user.social_handle, "@ali")
        self.assertEqual(res.json()["bio"], "سلام")

    def test_patch_is_partial(self):
        self.user.bio = "قدیمی"
        self.user.save()
        self.client.patch(reverse("api_me"), {"location": "شیراز"}, format="json")
        self.user.refresh_from_db()
        self.assertEqual(self.user.bio, "قدیمی")  # untouched
        self.assertEqual(self.user.location, "شیراز")

    def test_patch_rejects_long_bio(self):
        res = self.client.patch(
            reverse("api_me"),
            {"bio": "a" * (acc_consts.BIO_MAX_LENGTH + 1)}, format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_set_and_clear_favorite_team(self):
        team = make_team(self.comp, name="ایران")
        self.client.patch(reverse("api_me"),
                          {"favorite_team_id": team.id}, format="json")
        self.user.refresh_from_db()
        self.assertEqual(self.user.favorite_team_id, team.id)
        body = self.client.patch(reverse("api_me"),
                                {"favorite_team_id": None}, format="json").json()
        self.assertIsNone(body["favorite_team"])
        self.user.refresh_from_db()
        self.assertIsNone(self.user.favorite_team_id)

    def test_invalid_favorite_team(self):
        res = self.client.patch(reverse("api_me"),
                               {"favorite_team_id": 999999}, format="json")
        self.assertEqual(res.status_code, 400)


class AvatarUploadTests(AuthedTestCase):
    def setUp(self):
        super().setUp()
        # Write avatars to a throwaway dir so tests never touch the repo's media/.
        tmp = tempfile.mkdtemp()
        override = override_settings(MEDIA_ROOT=tmp)
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)

    def test_upload_avatar(self):
        res = self.client.post(reverse("api_my_avatar"),
                              {"avatar": _png_upload()}, format="multipart")
        self.assertEqual(res.status_code, 200)
        self.assertIsNotNone(res.json()["avatar"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar.name.startswith("avatars/"))

    def test_upload_requires_file(self):
        res = self.client.post(reverse("api_my_avatar"), {}, format="multipart")
        self.assertEqual(res.status_code, 400)

    def test_rejects_non_image_content_type(self):
        bad = SimpleUploadedFile("a.txt", b"hi", content_type="text/plain")
        res = self.client.post(reverse("api_my_avatar"),
                              {"avatar": bad}, format="multipart")
        self.assertEqual(res.status_code, 400)

    def test_rejects_fake_image(self):
        # Declared image/png but not a decodable image -> PIL verify fails.
        fake = SimpleUploadedFile("a.png", b"not an image", content_type="image/png")
        res = self.client.post(reverse("api_my_avatar"),
                              {"avatar": fake}, format="multipart")
        self.assertEqual(res.status_code, 400)

    def test_rejects_too_large(self):
        with mock.patch("accounts.consts.AVATAR_MAX_BYTES", 5):
            res = self.client.post(reverse("api_my_avatar"),
                                  {"avatar": _png_upload()}, format="multipart")
        self.assertEqual(res.status_code, 400)

    def test_delete_avatar(self):
        self.client.post(reverse("api_my_avatar"),
                        {"avatar": _png_upload()}, format="multipart")
        res = self.client.delete(reverse("api_my_avatar"))
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()["avatar"])
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)


class TeamsApiTests(AuthedTestCase):
    def test_lists_active_competition_teams(self):
        make_team(self.comp, name="ایران")
        body = self.client.get(reverse("api_teams")).json()
        self.assertTrue(any(t["name"] == "ایران" for t in body))


class PlayersDirectoryTests(AuthedTestCase):
    def test_players_lists_active_users_only(self):
        other = make_user(display_name="سارا")
        inactive = make_user(display_name="غایب", is_active=False)
        body = self.client.get(reverse("api_players")).json()
        ids = [p["id"] for p in body]
        self.assertIn(self.user.id, ids)
        self.assertIn(other.id, ids)
        self.assertNotIn(inactive.id, ids)
        self.assertIn("league_count", body[0])

    def test_players_league_count(self):
        make_league(self.comp, owner=self.user)
        body = self.client.get(reverse("api_players")).json()
        mine = next(p for p in body if p["id"] == self.user.id)
        self.assertEqual(mine["league_count"], 1)


class PlayerDetailTests(AuthedTestCase):
    def test_self_profile(self):
        body = self.client.get(
            reverse("api_player_detail", args=[self.user.id])
        ).json()
        self.assertTrue(body["is_me"])
        self.assertEqual(body["profile"]["id"], self.user.id)

    def test_shared_leagues_and_stats(self):
        league = make_league(self.comp, owner=self.user)
        other_m = join(league)
        match = make_match(self.comp)
        Prediction.objects.create(membership=other_m, match=match,
                                  predicted_home=1, predicted_away=0)
        body = self.client.get(
            reverse("api_player_detail", args=[other_m.user.id])
        ).json()
        self.assertFalse(body["is_me"])
        self.assertEqual(body["stats"]["leagues"], 1)
        self.assertEqual(body["stats"]["predictions"], 1)
        self.assertIn(league.slug, [l["slug"] for l in body["shared_leagues"]])

    def test_no_shared_league(self):
        other = make_user()
        body = self.client.get(
            reverse("api_player_detail", args=[other.id])
        ).json()
        self.assertEqual(body["shared_leagues"], [])

    def test_email_hidden_for_other_players(self):
        # Email is private: visible on my own profile, blank for anyone else.
        other = make_user(email="secret@test.com")
        body = self.client.get(
            reverse("api_player_detail", args=[other.id])
        ).json()
        self.assertEqual(body["profile"]["email"], "")
        mine = self.client.get(
            reverse("api_player_detail", args=[self.user.id])
        ).json()
        self.assertEqual(mine["profile"]["email"], "me@test.com")

    def test_missing_player_404(self):
        res = self.client.get(reverse("api_player_detail", args=[999999]))
        self.assertEqual(res.status_code, 404)


class LeagueMembersTests(AuthedTestCase):
    def test_members_list(self):
        league = make_league(self.comp, owner=self.user)
        join(league)
        body = self.client.get(
            reverse("api_league_members", args=[league.slug])
        ).json()
        self.assertEqual(len(body), 2)
        me_row = next(r for r in body if r["id"] == self.user.id)
        self.assertTrue(me_row["is_me"])
        self.assertEqual(me_row["role"], consts.Role.OWNER)
        self.assertIn("rank", me_row)
        self.assertIn("avatar", me_row)

    def test_non_member_cannot_list(self):
        league = make_league(self.comp)  # owned by someone else
        res = self.client.get(reverse("api_league_members", args=[league.slug]))
        self.assertEqual(res.status_code, 404)
