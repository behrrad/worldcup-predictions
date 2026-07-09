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
        # Kicked off 10 min ago -> closed.
        m = make_match(self.comp, kickoff=self.now - timedelta(minutes=10))
        res = self.client.post(
            reverse("api_submit_predictions", args=[self.league.slug]),
            {"predictions": [{"match_id": m.id, "home": 1, "away": 0}]},
            format="json",
        )
        self.assertEqual(res.json()["saved"], 0)
        self.assertFalse(Prediction.objects.filter(match=m).exists())

    def test_open_until_kickoff_by_default(self):
        # The default lock is 0 minutes: a match starting in 5 minutes (which the
        # old 30-minute default would have locked) still accepts predictions.
        self.assertEqual(self.league.lock_minutes, consts.DEFAULT_LOCK_MINUTES)
        m = make_match(self.comp, kickoff=self.now + timedelta(minutes=5))
        res = self.client.post(
            reverse("api_submit_predictions", args=[self.league.slug]),
            {"predictions": [{"match_id": m.id, "home": 2, "away": 2}]},
            format="json",
        )
        self.assertEqual(res.json()["saved"], 1)
        self.assertTrue(Prediction.objects.filter(match=m).exists())

    def test_cannot_submit_exactly_at_lock_boundary(self):
        # Kickoff exactly lock_minutes away => the match is closed *from* that
        # moment on. With the default 0-minute lock, a match kicking off right
        # now must already reject new predictions.
        self.assertEqual(self.league.lock_minutes, consts.DEFAULT_LOCK_MINUTES)
        m = make_match(
            self.comp,
            kickoff=self.now + timedelta(minutes=self.league.lock_minutes),
        )
        res = self.client.post(
            reverse("api_submit_predictions", args=[self.league.slug]),
            {"predictions": [{"match_id": m.id, "home": 1, "away": 0}]},
            format="json",
        )
        self.assertEqual(res.json()["saved"], 0)
        self.assertFalse(Prediction.objects.filter(match=m).exists())

    def test_respects_custom_lock_minutes(self):
        # A league that overrides lock_minutes still locks early: with a
        # 30-minute lock a kickoff 10 minutes out is already closed.
        self.league.lock_minutes = 30
        self.league.save(update_fields=["lock_minutes"])
        m = make_match(self.comp, kickoff=self.now + timedelta(minutes=10))
        res = self.client.post(
            reverse("api_submit_predictions", args=[self.league.slug]),
            {"predictions": [{"match_id": m.id, "home": 1, "away": 0}]},
            format="json",
        )
        self.assertEqual(res.json()["saved"], 0)
        self.assertFalse(Prediction.objects.filter(match=m).exists())

    def test_cannot_update_existing_prediction_after_lock(self):
        # A prediction made while the match was open must NOT be editable once
        # the match has kicked off.
        mem = Membership.objects.get(league=self.league, user=self.user)
        m = make_match(self.comp, kickoff=self.now - timedelta(minutes=10))  # locked
        Prediction.objects.create(
            membership=mem, match=m, predicted_home=2, predicted_away=1
        )
        res = self.client.post(
            reverse("api_submit_predictions", args=[self.league.slug]),
            {"predictions": [{"match_id": m.id, "home": 3, "away": 0}]},
            format="json",
        )
        self.assertEqual(res.json()["saved"], 0)
        p = Prediction.objects.get(membership=mem, match=m)
        self.assertEqual((p.predicted_home, p.predicted_away), (2, 1))  # unchanged

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


class AdvancerSubmitTests(AuthedTestCase):
    """The knockout-draw advancer pick on prediction submit + read-back."""

    def setUp(self):
        super().setUp()
        self.league = make_league(self.comp, owner=self.user)
        self.now = timezone.now()
        self.url = reverse("api_submit_predictions", args=[self.league.slug])

    def _ko_match(self):
        return make_match(self.comp, stage=consts.Stage.ROUND_OF_16,
                          kickoff=self.now + timedelta(hours=2))

    def _post(self, m, home, away, advancer=None):
        item = {"match_id": m.id, "home": home, "away": away}
        if advancer is not None:
            item["advancer"] = advancer
        return self.client.post(self.url, {"predictions": [item]}, format="json")

    def test_advancer_saved_on_knockout_draw(self):
        m = self._ko_match()
        self.assertEqual(self._post(m, 1, 1, "HOME").json()["saved"], 1)
        self.assertEqual(
            Prediction.objects.get(match=m).predicted_advancer, consts.Advancer.HOME)

    def test_advancer_cleared_on_non_draw(self):
        m = self._ko_match()
        self._post(m, 2, 1, "HOME")
        self.assertEqual(
            Prediction.objects.get(match=m).predicted_advancer, consts.Advancer.NONE)

    def test_advancer_ignored_on_group_draw(self):
        m = make_match(self.comp, stage=consts.Stage.GROUP,
                       kickoff=self.now + timedelta(hours=2))
        self._post(m, 1, 1, "AWAY")
        self.assertEqual(
            Prediction.objects.get(match=m).predicted_advancer, consts.Advancer.NONE)

    def test_invalid_advancer_value_normalized_to_blank(self):
        m = self._ko_match()
        self._post(m, 0, 0, "garbage")
        self.assertEqual(
            Prediction.objects.get(match=m).predicted_advancer, consts.Advancer.NONE)

    def test_updating_draw_to_winner_clears_stale_advancer(self):
        m = self._ko_match()
        self._post(m, 1, 1, "HOME")
        self._post(m, 2, 0)  # decisive scoreline, no advancer
        p = Prediction.objects.get(match=m)
        self.assertEqual((p.predicted_home, p.predicted_away), (2, 0))
        self.assertEqual(p.predicted_advancer, consts.Advancer.NONE)

    def test_my_prediction_exposes_advancer(self):
        m = self._ko_match()
        self._post(m, 1, 1, "AWAY")
        body = self.client.get(
            reverse("api_league_matches", args=[self.league.slug])).json()
        row = next(x for x in body if x["id"] == m.id)
        self.assertEqual(row["my_prediction"]["advancer"], "AWAY")


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
        body = res.json()
        # Nothing in play: the live view mirrors the official one.
        self.assertFalse(body["is_live"])
        row = body["rows"][0]
        self.assertEqual(row["total"], 10.0)
        self.assertTrue(row["is_me"])
        self.assertEqual(row["live_total"], 10.0)
        self.assertEqual(row["live_rank"], row["rank"])
        self.assertEqual(row["live_points"], 0.0)
        # Average view: predicted the only finished game, 10 pts over 1 game.
        self.assertEqual(row["played"], 1)
        self.assertEqual(row["avg_points"], 10.0)
        self.assertTrue(row["eligible_for_avg"])
        self.assertEqual(row["avg_rank"], 1)

    def test_leaderboard_live_view_counts_in_play_score(self):
        league = make_league(self.comp, owner=self.user)
        mem = Membership.objects.get(league=league, user=self.user)
        m = make_match(self.comp)
        Prediction.objects.create(membership=mem, match=m, predicted_home=1, predicted_away=0)
        # In-play state arrives via queryset.update() (the live.py write path).
        Match.objects.filter(pk=m.pk).update(
            live_status=consts.LiveStatus.LIVE, live_home_score=1, live_away_score=0,
        )
        body = self.client.get(reverse("api_leaderboard", args=[league.slug])).json()
        self.assertTrue(body["is_live"])
        row = body["rows"][0]
        self.assertEqual(row["total"], 0.0)          # official: nothing yet
        self.assertEqual(row["live_points"], 10.0)   # exact on the live score
        self.assertEqual(row["live_total"], 10.0)
        self.assertEqual(row["live_rank"], 1)


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


class RevealPredictionsToggleTests(AuthedTestCase):
    """The league owner can hide other members' predictions even after lock."""

    def setUp(self):
        super().setUp()
        self.league = make_league(self.comp, owner=self.user)  # self.user is owner
        self.now = timezone.now()
        # A second member with a prediction on a match that has already locked.
        self.other = join(self.league)
        self.match = make_match(self.comp, kickoff=self.now - timedelta(minutes=5))
        Prediction.objects.create(
            membership=self.other, match=self.match,
            predicted_home=3, predicted_away=2,
        )

    def _match_body(self):
        return self.client.get(
            reverse("api_match_detail", args=[self.league.slug, self.match.id])
        ).json()

    def test_default_reveals_after_lock(self):
        # Default behaviour is unchanged: once locked, others' picks are shown.
        body = self._match_body()
        self.assertTrue(body["reveal_predictions"])
        self.assertTrue(body["revealed"])
        row = next(r for r in body["predictions"] if not r["is_me"])
        self.assertEqual((row["home"], row["away"]), (3, 2))

    def test_league_detail_exposes_flag(self):
        body = self.client.get(
            reverse("api_league_detail", args=[self.league.slug])
        ).json()
        self.assertTrue(body["reveal_predictions"])

    def test_owner_can_disable_reveal(self):
        res = self.client.patch(
            reverse("api_league_detail", args=[self.league.slug]),
            {"reveal_predictions": False}, format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["reveal_predictions"])
        self.league.refresh_from_db()
        self.assertFalse(self.league.reveal_predictions)

    def test_disabled_keeps_others_picks_hidden_after_lock(self):
        self.league.reveal_predictions = False
        self.league.save(update_fields=["reveal_predictions"])
        body = self._match_body()
        # The match is locked, yet picks stay hidden because the owner turned
        # reveal off. The predictor is still listed by name (participation), but
        # the actual score is withheld.
        self.assertFalse(body["revealed"])
        self.assertFalse(body["reveal_predictions"])
        row = next(r for r in body["predictions"] if not r["is_me"])
        self.assertIsNone(row["home"])
        self.assertIsNone(row["away"])

    def test_non_owner_cannot_toggle(self):
        member_client = APIClient()
        member_client.force_authenticate(user=self.other.user)
        res = member_client.patch(
            reverse("api_league_detail", args=[self.league.slug]),
            {"reveal_predictions": False}, format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.league.refresh_from_db()
        self.assertTrue(self.league.reveal_predictions)  # unchanged


class BoostOptInTests(AuthedTestCase):
    """The owner-gated 2× knockout-boost opt-in on league_detail PATCH."""

    def setUp(self):
        super().setUp()
        self.league = make_league(self.comp, owner=self.user)
        self.other = join(self.league)

    def _url(self):
        return reverse("api_league_detail", args=[self.league.slug])

    def test_default_is_pending(self):
        body = self.client.get(self._url()).json()
        self.assertEqual(body["boost_decision"], consts.BoostDecision.PENDING)

    def test_owner_accept_doubles_qf_onward(self):
        res = self.client.patch(self._url(), {"boost_decision": "accept"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["boost_decision"], consts.BoostDecision.ACCEPTED)
        self.league.refresh_from_db()
        self.assertEqual(self.league.multiplier_qf, consts.BOOST_TARGET_MULTIPLIER)
        self.assertEqual(self.league.multiplier_sf, consts.BOOST_TARGET_MULTIPLIER)
        self.assertEqual(self.league.multiplier_tp, consts.BOOST_TARGET_MULTIPLIER)
        self.assertEqual(self.league.multiplier_final, consts.BOOST_TARGET_MULTIPLIER)
        # Earlier rounds are untouched.
        self.assertEqual(self.league.multiplier_r16, consts.DEFAULT_KNOCKOUT_MULTIPLIER)

    def test_owner_decline_keeps_multipliers(self):
        res = self.client.patch(self._url(), {"boost_decision": "decline"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["boost_decision"], consts.BoostDecision.DECLINED)
        self.league.refresh_from_db()
        self.assertEqual(self.league.multiplier_qf, consts.DEFAULT_KNOCKOUT_MULTIPLIER)

    def test_invalid_value_is_rejected(self):
        res = self.client.patch(self._url(), {"boost_decision": "maybe"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.league.refresh_from_db()
        self.assertEqual(self.league.boost_decision, consts.BoostDecision.PENDING)

    def test_non_owner_cannot_decide(self):
        member_client = APIClient()
        member_client.force_authenticate(user=self.other.user)
        res = member_client.patch(self._url(), {"boost_decision": "accept"}, format="json")
        self.assertEqual(res.status_code, 403)
        self.league.refresh_from_db()
        self.assertEqual(self.league.boost_decision, consts.BoostDecision.PENDING)
        self.assertEqual(self.league.multiplier_qf, consts.DEFAULT_KNOCKOUT_MULTIPLIER)

    def test_default_multiplier_exposed(self):
        body = self.client.get(self._url()).json()
        self.assertEqual(body["boost_multiplier"], 1.5)

    def test_owner_sets_custom_multiplier(self):
        res = self.client.patch(self._url(), {"boost_multiplier": 2.5}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["boost_multiplier"], 2.5)
        self.assertEqual(res.json()["boost_decision"], consts.BoostDecision.ACCEPTED)
        self.league.refresh_from_db()
        from decimal import Decimal
        self.assertEqual(self.league.multiplier_qf, Decimal("2.50"))
        self.assertEqual(self.league.multiplier_final, Decimal("2.50"))
        # Earlier rounds untouched.
        self.assertEqual(self.league.multiplier_r16, consts.DEFAULT_KNOCKOUT_MULTIPLIER)

    def test_custom_multiplier_out_of_range_rejected(self):
        res = self.client.patch(self._url(), {"boost_multiplier": 10}, format="json")
        self.assertEqual(res.status_code, 400)
        self.league.refresh_from_db()
        self.assertEqual(self.league.multiplier_qf, consts.DEFAULT_KNOCKOUT_MULTIPLIER)

    def test_custom_multiplier_non_numeric_rejected(self):
        res = self.client.patch(self._url(), {"boost_multiplier": "abc"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_non_owner_cannot_set_multiplier(self):
        member_client = APIClient()
        member_client.force_authenticate(user=self.other.user)
        res = member_client.patch(self._url(), {"boost_multiplier": 2.5}, format="json")
        self.assertEqual(res.status_code, 403)
        self.league.refresh_from_db()
        self.assertEqual(self.league.multiplier_qf, consts.DEFAULT_KNOCKOUT_MULTIPLIER)


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

    def test_counts_for_scoring_flag_in_payload(self):
        normal = make_match(self.comp, kickoff=timezone.now() + timedelta(days=1))
        voided = make_match(self.comp, kickoff=timezone.now() + timedelta(days=2),
                            count_for_scoring=False)
        res = self.client.get(reverse("api_league_matches", args=[self.league.slug]))
        by_id = {m["id"]: m for m in res.json()}
        self.assertTrue(by_id[normal.id]["counts_for_scoring"])
        self.assertFalse(by_id[voided.id]["counts_for_scoring"])


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


class ProgressionApiTests(AuthedTestCase):
    """The points/rank progression feed: cumulative totals and ranks replayed
    match by match, one aligned series per member."""

    def setUp(self):
        super().setUp()
        self.league = make_league(self.comp, owner=self.user)  # self.user is owner
        self.me = Membership.objects.get(league=self.league, user=self.user)
        self.other = join(self.league)
        self.now = timezone.now()

    def _body(self):
        return self.client.get(
            reverse("api_league_progression", args=[self.league.slug])
        ).json()

    def _player(self, body, *, is_me):
        return next(p for p in body["players"] if p["is_me"] is is_me)

    def test_empty_until_a_match_finishes(self):
        # No finished matches yet: no steps, members present with empty series.
        make_match(self.comp, kickoff=self.now + timedelta(days=1))
        body = self._body()
        self.assertEqual(body["steps"], [])
        self.assertEqual(len(body["players"]), 2)
        me = self._player(body, is_me=True)
        self.assertEqual(me["totals"], [])
        self.assertIsNone(me["rank"])

    def test_cumulative_totals_and_ranks_move_per_match(self):
        # Two finished matches in chronological order. I nail the first exactly;
        # the other member nails the second — so we swap from a clear lead to a tie.
        m1 = make_match(self.comp, kickoff=self.now - timedelta(days=2))
        m2 = make_match(self.comp, kickoff=self.now - timedelta(days=1))
        Prediction.objects.create(membership=self.me, match=m1, predicted_home=2, predicted_away=1)
        Prediction.objects.create(membership=self.other, match=m2, predicted_home=1, predicted_away=0)
        # Saving each result triggers the scoring recompute for every member.
        m1.home_score, m1.away_score = 2, 1
        m1.save()
        m2.home_score, m2.away_score = 1, 0
        m2.save()

        body = self._body()
        # Steps are the finished matches, oldest first.
        self.assertEqual(len(body["steps"]), 2)
        self.assertEqual(body["steps"][0]["home_score"], 2)
        self.assertEqual(body["steps"][1]["home_score"], 1)

        me = self._player(body, is_me=True)
        other = self._player(body, is_me=False)
        # I lead after match 1, then the other catches up to a tie after match 2.
        self.assertEqual(me["match_points"], [10.0, 0.0])
        self.assertEqual(me["totals"], [10.0, 10.0])
        # Ties share a rank (tie-broken by join order), so I keep the shared lead.
        self.assertEqual(me["ranks"], [1, 1])
        self.assertEqual(other["match_points"], [0.0, 10.0])
        self.assertEqual(other["totals"], [0.0, 10.0])
        self.assertEqual(other["ranks"], [2, 1])  # the other climbs into the tie
        # `played` counts only matches each member actually predicted (the
        # average's denominator): I predicted m1 only, the other m2 only.
        self.assertEqual(me["played"], [1, 1])
        self.assertEqual(other["played"], [0, 1])
        # Final standing fields mirror the last step.
        self.assertEqual(me["total"], 10.0)

    def test_non_member_gets_404(self):
        league = make_league(self.comp)  # owned by someone else
        res = self.client.get(reverse("api_league_progression", args=[league.slug]))
        self.assertEqual(res.status_code, 404)


class PlayerAverageApiTests(AuthedTestCase):
    """The profile chart: a player's average points-per-prediction over time,
    pooled across every league they belong to."""

    def test_empty_when_no_finished_predictions(self):
        body = self.client.get(
            reverse("api_player_average", args=[self.user.id])
        ).json()
        self.assertEqual(body["steps"], [])
        self.assertEqual(body["series"]["averages"], [])

    def test_average_pools_predictions_across_leagues(self):
        now = timezone.now()
        a = make_league(self.comp, owner=self.user, name="لیگ آ")
        b = make_league(self.comp, owner=self.user, name="لیگ ب")
        ma = Membership.objects.get(league=a, user=self.user)
        mb = Membership.objects.get(league=b, user=self.user)
        m1 = make_match(self.comp, kickoff=now - timedelta(days=2))
        m2 = make_match(self.comp, kickoff=now - timedelta(days=1))
        # m1: exact in both leagues (10 + 10).
        Prediction.objects.create(membership=ma, match=m1, predicted_home=2, predicted_away=1)
        Prediction.objects.create(membership=mb, match=m1, predicted_home=2, predicted_away=1)
        # m2: exact in A (10), winner-only in B (5).
        Prediction.objects.create(membership=ma, match=m2, predicted_home=1, predicted_away=0)
        Prediction.objects.create(membership=mb, match=m2, predicted_home=2, predicted_away=0)
        m1.home_score, m1.away_score = 2, 1
        m1.save()
        m2.home_score, m2.away_score = 1, 0
        m2.save()

        body = self.client.get(
            reverse("api_player_average", args=[self.user.id])
        ).json()
        self.assertEqual(len(body["steps"]), 2)
        # Each league is its own prediction: 2 after m1, 4 after m2.
        self.assertEqual(body["series"]["played"], [2, 4])
        self.assertEqual(body["series"]["totals"], [20.0, 35.0])
        # Pooled mean: 20/2 = 10.0, then 35/4 = 8.75.
        self.assertEqual(body["series"]["averages"], [10.0, 8.75])

    def test_unknown_player_404(self):
        res = self.client.get(reverse("api_player_average", args=[999999]))
        self.assertEqual(res.status_code, 404)


class AllPredictionsApiTests(AuthedTestCase):
    """The 'Everyone's predictions' board aggregates picks across all matches,
    honouring the same per-match reveal rules as the match-detail view."""

    def setUp(self):
        super().setUp()
        self.league = make_league(self.comp, owner=self.user)
        self.me = Membership.objects.get(league=self.league, user=self.user)
        self.other = join(self.league)
        self.now = timezone.now()

    def _body(self):
        return self.client.get(
            reverse("api_league_all_predictions", args=[self.league.slug])
        ).json()

    def test_revealed_finished_match_shows_picks_and_points(self):
        m = make_match(self.comp, kickoff=self.now - timedelta(minutes=40))
        Prediction.objects.create(membership=self.me, match=m, predicted_home=2, predicted_away=1)
        Prediction.objects.create(membership=self.other, match=m, predicted_home=0, predicted_away=0)
        m.home_score, m.away_score = 2, 1
        m.save()  # finished -> scores computed via signal

        body = self._body()
        self.assertEqual(body["member_count"], 2)
        row = next(r for r in body["matches"] if r["id"] == m.id)
        self.assertTrue(row["revealed"])
        self.assertEqual(row["predicted_count"], 2)
        me = next(p for p in row["predictions"] if p["is_me"])
        self.assertEqual((me["home"], me["away"]), (2, 1))
        self.assertEqual(me["points"], 10.0)  # exact, group ×1.0
        self.assertEqual(me["tier"], consts.Tier.EXACT)

    def test_open_match_hides_picks_but_counts_participation(self):
        m = make_match(self.comp, kickoff=self.now + timedelta(hours=2))  # open
        Prediction.objects.create(membership=self.other, match=m, predicted_home=3, predicted_away=2)
        row = next(r for r in self._body()["matches"] if r["id"] == m.id)
        self.assertFalse(row["revealed"])
        self.assertTrue(row["is_open"])                     # genuinely still open
        self.assertEqual(row["predicted_count"], 1)         # participation shown
        self.assertIsNone(row["predictions"][0]["home"])    # pick withheld
        self.assertIsNone(row["predictions"][0]["away"])

    def test_reveal_off_hides_picks_even_after_lock(self):
        self.league.reveal_predictions = False
        self.league.save(update_fields=["reveal_predictions"])
        m = make_match(self.comp, kickoff=self.now - timedelta(minutes=5))  # locked
        Prediction.objects.create(membership=self.other, match=m, predicted_home=1, predicted_away=0)
        body = self._body()
        self.assertFalse(body["reveal_predictions"])
        row = next(r for r in body["matches"] if r["id"] == m.id)
        self.assertFalse(row["revealed"])
        # Locked, not open -> the UI groups it as "private", not "upcoming".
        self.assertFalse(row["is_open"])
        self.assertIsNone(row["predictions"][0]["home"])

    def test_non_member_gets_404(self):
        other_league = make_league(self.comp)  # not joined
        res = self.client.get(
            reverse("api_league_all_predictions", args=[other_league.slug])
        )
        self.assertEqual(res.status_code, 404)
