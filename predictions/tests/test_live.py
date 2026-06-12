"""Tests for the live (in-play) scores pipeline: provider parsing, matching,
the queryset-only write rule, the staleness/claim gate, and the API endpoint.

The provider fixtures under tests/data/ are trimmed copies of real responses
captured on 2026-06-12 while Canada–Bosnia was actually in play."""
import json
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from predictions import consts, live
from predictions.models import Competition, Match, MatchScore

from .factories import make_competition, make_league, make_match, make_team

DATA_DIR = Path(__file__).parent / "data"


def _fixture(name):
    return json.loads((DATA_DIR / name).read_text())


def _patch_fetch(payload):
    """Patch the HTTP layer so a parser sees `payload` as the response."""
    return mock.patch.object(live, "_get_json", return_value=payload)


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
class EspnParserTests(TestCase):
    def test_real_fixture(self):
        """The captured scoreboard: one live match (54'), one not started."""
        with _patch_fetch(_fixture("espn_scoreboard.json")):
            rows = live.fetch_espn()
        self.assertEqual(len(rows), 1)  # the "pre" event is skipped
        row = rows[0]
        self.assertEqual(row["status"], consts.LiveStatus.LIVE)
        self.assertEqual(row["minute"], "54")
        self.assertEqual((row["home_code"], row["away_code"]), ("CAN", "BIH"))
        self.assertEqual((row["home_score"], row["away_score"]), (0, 1))
        self.assertEqual(row["kickoff"].isoformat(), "2026-06-12T19:00:00+00:00")

    def _event(self, state, type_name="", clock="54'", scores=("0", "1")):
        return {"events": [{
            "date": "2026-06-12T19:00Z",
            "competitions": [{
                "competitors": [
                    {"homeAway": "home", "score": scores[0],
                     "team": {"abbreviation": "CAN", "displayName": "Canada"}},
                    {"homeAway": "away", "score": scores[1],
                     "team": {"abbreviation": "BIH",
                              "displayName": "Bosnia-Herzegovina"}},
                ],
                "status": {"displayClock": clock,
                           "type": {"state": state, "name": type_name}},
            }],
        }]}

    def test_halftime_and_fulltime(self):
        with _patch_fetch(self._event("in", consts.ESPN_STATUS_HALFTIME, "45'")):
            (row,) = live.fetch_espn()
        self.assertEqual(row["status"], consts.LiveStatus.HALFTIME)
        self.assertEqual(row["minute"], "")  # clock only meaningful in play

        with _patch_fetch(self._event("post", "STATUS_FULL_TIME", "90'")):
            (row,) = live.fetch_espn()
        self.assertEqual(row["status"], consts.LiveStatus.FULL_TIME)

    def test_stoppage_time_clock(self):
        with _patch_fetch(self._event("in", clock="45'+4'")):
            (row,) = live.fetch_espn()
        self.assertEqual(row["minute"], "45+4")

    def test_malformed_events_are_skipped(self):
        broken = self._event("in")
        broken["events"][0]["competitions"][0]["competitors"][0]["score"] = "abc"
        broken["events"].append({"date": "not-a-date"})  # missing everything
        with _patch_fetch(broken):
            self.assertEqual(live.fetch_espn(), [])

    def test_unexpected_payload_raises(self):
        with _patch_fetch([1, 2, 3]):
            with self.assertRaises(live.LiveFetchError):
                live.fetch_espn()


class Varzesh3ParserTests(TestCase):
    def test_real_fixture(self):
        """Captured feed: KOR–CZE finished 2–1, CAN–BIH live 55', one match
        not started, and a whole volleyball league to be ignored."""
        with _patch_fetch(_fixture("varzesh3_livescore.json")):
            rows = live.fetch_varzesh3()
        self.assertEqual(len(rows), 2)
        finished, in_play = rows
        self.assertEqual(finished["status"], consts.LiveStatus.FULL_TIME)
        self.assertEqual((finished["home_score"], finished["away_score"]), (2, 1))
        self.assertEqual(finished["home_fa"], "کره جنوبی")
        self.assertEqual(in_play["status"], consts.LiveStatus.LIVE)
        self.assertEqual(in_play["minute"], "55")
        self.assertEqual((in_play["home_fa"], in_play["away_fa"]),
                         ("کانادا", "بوسنی"))

    def test_halftime(self):
        payload = [{"sport": consts.VARZESH3_SPORT_FOOTBALL, "dates": [{"matches": [{
            "startOnUtc": "2026-06-12T19:00:00Z",
            "status": consts.Varzesh3Status.LIVE,
            "statusTitle": consts.VARZESH3_HALFTIME_TITLE,
            "liveTime": "",
            "goals": {"host": 0, "guest": 1},
            "host": {"id": 1, "name": "کانادا"},
            "guest": {"id": 2, "name": "بوسنی"},
        }]}]}]
        with _patch_fetch(payload):
            (row,) = live.fetch_varzesh3()
        self.assertEqual(row["status"], consts.LiveStatus.HALFTIME)

    def test_unexpected_payload_raises(self):
        with _patch_fetch({"oops": True}):
            with self.assertRaises(live.LiveFetchError):
                live.fetch_varzesh3()


# --------------------------------------------------------------------------- #
# Matching + applying snapshots
# --------------------------------------------------------------------------- #
class ApplySnapshotTests(TestCase):
    def setUp(self):
        self.comp = make_competition()
        self.now = timezone.now()
        self.canada = make_team(self.comp, name="کانادا", name_en="Canada", code="CAN")
        self.bosnia = make_team(
            self.comp, name="بوسنی و هرزگوین", name_en="Bosnia and Herzegovina",
            code="BIH",
        )
        self.match = make_match(
            self.comp, home=self.canada, away=self.bosnia,
            kickoff=self.now - timedelta(hours=1),
        )

    def _row(self, **kw):
        base = dict(
            kickoff=self.match.kickoff, status=consts.LiveStatus.LIVE,
            minute="54", home_score=0, away_score=1,
            home_code="CAN", away_code="BIH",
            home_en="canada", away_en="bosnia-herzegovina",
            home_fa="", away_fa="",
        )
        base.update(kw)
        return base

    def test_apply_by_code_writes_live_fields_only(self):
        written = live.apply_snapshot(self.comp, [self._row()], self.now)
        self.assertEqual(written, 1)
        self.match.refresh_from_db()
        self.assertEqual(self.match.live_home_score, 0)
        self.assertEqual(self.match.live_away_score, 1)
        self.assertEqual(self.match.live_minute, "54")
        self.assertEqual(self.match.live_status, consts.LiveStatus.LIVE)
        # The hard rule: live data never touches the result or the scoring.
        self.assertIsNone(self.match.home_score)
        self.assertEqual(self.match.status, consts.MatchStatus.SCHEDULED)
        self.assertEqual(MatchScore.objects.count(), 0)

    def test_apply_is_idempotent(self):
        live.apply_snapshot(self.comp, [self._row()], self.now)
        written = live.apply_snapshot(self.comp, [self._row()], self.now)
        self.assertEqual(written, 0)  # unchanged state -> no write

    def test_swapped_home_away_flips_scores(self):
        row = self._row(home_code="BIH", away_code="CAN",
                        home_en="bosnia-herzegovina", away_en="canada",
                        home_score=1, away_score=0)
        live.apply_snapshot(self.comp, [row], self.now)
        self.match.refresh_from_db()
        self.assertEqual(self.match.live_home_score, 0)  # Canada is our home
        self.assertEqual(self.match.live_away_score, 1)

    def test_persian_containment_matching(self):
        """Varzesh3 says «بوسنی»; our team is «بوسنی و هرزگوین»."""
        row = self._row(home_code=None, away_code=None, home_en="", away_en="",
                        home_fa="کانادا", away_fa="بوسنی")
        live.apply_snapshot(self.comp, [row], self.now)
        self.match.refresh_from_db()
        self.assertEqual(self.match.live_status, consts.LiveStatus.LIVE)

    def test_simultaneous_kickoffs_disambiguated_by_name(self):
        """Final group rounds: several matches share one kickoff."""
        mexico = make_team(self.comp, name="مکزیک", name_en="Mexico", code="MEX")
        korea = make_team(self.comp, name="کره جنوبی", name_en="South Korea",
                          code="KOR")
        other = make_match(self.comp, home=mexico, away=korea,
                           kickoff=self.match.kickoff)
        row = self._row(home_code=None, away_code=None, home_en="", away_en="",
                        home_fa="مکزیک", away_fa="کره جنوبی",
                        home_score=3, away_score=2, minute="60")
        live.apply_snapshot(self.comp, [row], self.now)
        other.refresh_from_db()
        self.match.refresh_from_db()
        self.assertEqual(other.live_home_score, 3)
        self.assertEqual(self.match.live_status, consts.LiveStatus.NONE)

    def test_kickoff_window_guards_rematches(self):
        """A result whose date is far from our kickoff never applies."""
        row = self._row(kickoff=self.match.kickoff - timedelta(days=30))
        written = live.apply_snapshot(self.comp, [row], self.now)
        self.assertEqual(written, 0)

    def test_officially_finished_matches_are_ignored(self):
        self.match.home_score, self.match.away_score = 2, 2
        self.match.save()
        row = self._row(status=consts.LiveStatus.FULL_TIME, minute="")
        written = live.apply_snapshot(self.comp, [row], self.now)
        self.assertEqual(written, 0)

    def test_vanished_fulltime_state_is_cleared(self):
        Match.objects.filter(pk=self.match.pk).update(
            live_status=consts.LiveStatus.FULL_TIME, live_home_score=0,
            live_away_score=1, live_updated_at=self.now,
        )
        live.apply_snapshot(self.comp, [], self.now)  # provider rolled over
        self.match.refresh_from_db()
        self.assertEqual(self.match.live_status, consts.LiveStatus.NONE)
        self.assertIsNone(self.match.live_home_score)

    def test_vanished_in_play_state_survives_until_stale(self):
        recent = self.now - timedelta(seconds=consts.LIVE_STALE_CLEAR_SECONDS // 2)
        Match.objects.filter(pk=self.match.pk).update(
            live_status=consts.LiveStatus.LIVE, live_minute="54",
            live_updated_at=recent,
        )
        live.apply_snapshot(self.comp, [], self.now)  # one flaky empty response
        self.match.refresh_from_db()
        self.assertEqual(self.match.live_status, consts.LiveStatus.LIVE)

        stale = self.now - timedelta(seconds=consts.LIVE_STALE_CLEAR_SECONDS + 1)
        Match.objects.filter(pk=self.match.pk).update(live_updated_at=stale)
        live.apply_snapshot(self.comp, [], self.now)
        self.match.refresh_from_db()
        self.assertEqual(self.match.live_status, consts.LiveStatus.NONE)


# --------------------------------------------------------------------------- #
# The refresh gate (claim + window)
# --------------------------------------------------------------------------- #
class RefreshGateTests(TestCase):
    def setUp(self):
        self.comp = make_competition()
        self.now = timezone.now()
        self.match = make_match(self.comp, kickoff=self.now - timedelta(hours=1))

    def test_claim_allows_one_fetch_per_window(self):
        with mock.patch.object(live, "fetch_espn", return_value=[]) as fetcher:
            self.assertTrue(live.refresh_if_stale(self.comp, self.now))
            self.assertFalse(live.refresh_if_stale(self.comp, self.now))
        self.assertEqual(fetcher.call_count, 1)

    def test_stale_stamp_allows_refetch(self):
        Competition.objects.filter(pk=self.comp.pk).update(
            live_checked_at=self.now
            - timedelta(seconds=consts.LIVE_REFRESH_SECONDS + 1)
        )
        with mock.patch.object(live, "fetch_espn", return_value=[]):
            self.assertTrue(live.refresh_if_stale(self.comp, self.now))

    def test_no_fetch_outside_live_window(self):
        Match.objects.filter(pk=self.match.pk).update(
            kickoff=self.now + timedelta(days=2)
        )
        with mock.patch.object(live, "fetch_espn") as fetcher:
            self.assertFalse(live.refresh_if_stale(self.comp, self.now))
        fetcher.assert_not_called()

    def test_in_play_state_keeps_window_open(self):
        """Extra time/penalties: live state extends polling past the window."""
        Match.objects.filter(pk=self.match.pk).update(
            kickoff=self.now - timedelta(hours=12),
            live_status=consts.LiveStatus.LIVE,
        )
        with mock.patch.object(live, "fetch_espn", return_value=[]) as fetcher:
            self.assertTrue(live.refresh_if_stale(self.comp, self.now))
        fetcher.assert_called_once()

    def test_fallback_provider_on_primary_failure(self):
        with mock.patch.object(
            live, "fetch_espn", side_effect=live.LiveFetchError("down")
        ), mock.patch.object(
            live, "fetch_varzesh3", return_value=[]
        ) as fallback:
            self.assertTrue(live.refresh_if_stale(self.comp, self.now))
        fallback.assert_called_once()

    def test_all_providers_failing_degrades_quietly(self):
        with mock.patch.object(
            live, "fetch_espn", side_effect=live.LiveFetchError("down")
        ), mock.patch.object(
            live, "fetch_varzesh3", side_effect=live.LiveFetchError("down")
        ):
            self.assertFalse(live.refresh_if_stale(self.comp, self.now))


# --------------------------------------------------------------------------- #
# API endpoint + serialization
# --------------------------------------------------------------------------- #
class LiveApiTests(APITestCase):
    def setUp(self):
        self.comp = make_competition()
        self.league = make_league(self.comp)
        self.user = self.league.owner
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.now = timezone.now()
        self.match = make_match(self.comp, kickoff=self.now - timedelta(hours=1))

    def _set_live(self, match, **kw):
        state = dict(
            live_status=consts.LiveStatus.LIVE, live_minute="54",
            live_home_score=0, live_away_score=1, live_updated_at=self.now,
        )
        state.update(kw)
        Match.objects.filter(pk=match.pk).update(**state)

    def test_requires_auth(self):
        self.assertEqual(APIClient().get(reverse("api_live_scores")).status_code, 401)

    def test_live_endpoint_shape(self):
        self._set_live(self.match)
        with mock.patch.object(live, "refresh_if_stale") as refresh:
            res = self.client.get(reverse("api_live_scores"))
        refresh.assert_called_once()
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("checked_at", data)
        (entry,) = data["matches"]
        self.assertEqual(entry["id"], self.match.id)
        self.assertEqual(entry["status"], consts.LiveStatus.LIVE)
        self.assertEqual(
            entry["status_label"],
            consts.LIVE_STATUS_LABELS[consts.LiveStatus.LIVE],
        )
        self.assertEqual(entry["minute"], "54")
        self.assertEqual((entry["home"], entry["away"]), (0, 1))
        self.assertIn("name", entry["home_team"])

    def test_finished_matches_never_listed(self):
        self._set_live(self.match, live_status=consts.LiveStatus.FULL_TIME)
        self.match.home_score, self.match.away_score = 0, 1
        self.match.save()
        with mock.patch.object(live, "refresh_if_stale"):
            res = self.client.get(reverse("api_live_scores"))
        self.assertEqual(res.json()["matches"], [])

    def test_match_dict_carries_live_state(self):
        self._set_live(self.match)
        res = self.client.get(
            reverse("api_league_matches", args=[self.league.slug])
        )
        (entry,) = [m for m in res.json() if m["id"] == self.match.id]
        self.assertEqual(entry["live"]["minute"], "54")
        self.assertEqual(entry["live"]["home"], 0)

    def test_match_dict_live_is_null_when_finished_or_absent(self):
        res = self.client.get(
            reverse("api_league_matches", args=[self.league.slug])
        )
        (entry,) = [m for m in res.json() if m["id"] == self.match.id]
        self.assertIsNone(entry["live"])
