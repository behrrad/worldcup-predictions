from datetime import datetime, timedelta, timezone as utc_tz
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from predictions import consts
from predictions.models import League, MatchScore, Membership, Prediction
from .factories import make_competition, make_match, make_team, make_user

FETCH = "predictions.management.commands.sync_results.fetch_matches"


def api_match(home_tla, away_tla, hs, as_, *, home_name="", away_name="",
              status="FINISHED", utc="2026-06-11T19:00:00Z"):
    return {
        "status": status,
        "utcDate": utc,
        "homeTeam": {"tla": home_tla, "name": home_name},
        "awayTeam": {"tla": away_tla, "name": away_name},
        "score": {"fullTime": {"home": hs, "away": as_}},
    }


class SyncResultsTests(TestCase):
    def setUp(self):
        self.comp = make_competition()
        self.home = make_team(self.comp, name="مکزیک", code="MEX", name_en="Mexico")
        self.away = make_team(self.comp, name="آفریقای جنوبی", code="RSA", name_en="South Africa")
        # Fixed kickoff matching the api_match default date, so results fall inside
        # the sync's date-match window.
        self.match = make_match(
            self.comp, home=self.home, away=self.away, match_number=1,
            kickoff=datetime(2026, 6, 11, 19, 0, tzinfo=utc_tz.utc),
        )
        # A member who predicted the exact score, so recompute should award points.
        self.user = make_user()
        self.league = League.objects.create(name="L", competition=self.comp, owner=self.user)
        self.mem = Membership.objects.create(
            league=self.league, user=self.user, role=consts.Role.OWNER
        )
        Prediction.objects.create(
            membership=self.mem, match=self.match, predicted_home=2, predicted_away=1
        )

    def _run(self, payload, **kw):
        kw.setdefault("competition", self.comp.slug)
        with mock.patch(FETCH, return_value=payload):
            call_command("sync_results", token="t", verbosity=0, **kw)

    def test_updates_scores_and_recomputes(self):
        self._run({"matches": [api_match("MEX", "RSA", 2, 1)]})
        self.match.refresh_from_db()
        self.assertEqual((self.match.home_score, self.match.away_score), (2, 1))
        self.assertTrue(self.match.is_finished)
        # recompute fired via the post_save signal -> the exact prediction scored
        score = MatchScore.objects.get(membership=self.mem, match=self.match)
        self.assertEqual(score.tier, consts.Tier.EXACT)
        self.assertGreater(score.points, 0)

    def test_idempotent_rerun_reports_unchanged(self):
        payload = {"matches": [api_match("MEX", "RSA", 2, 1)]}
        self._run(payload)
        with mock.patch(FETCH, return_value=payload):
            # second run shouldn't change anything; spy on save to be sure
            with mock.patch("predictions.models.Match.save") as saved:
                call_command("sync_results", token="t", competition=self.comp.slug, verbosity=0)
                saved.assert_not_called()

    def test_dry_run_makes_no_changes(self):
        self._run({"matches": [api_match("MEX", "RSA", 3, 0)]}, dry_run=True)
        self.match.refresh_from_db()
        self.assertIsNone(self.match.home_score)
        self.assertFalse(MatchScore.objects.filter(match=self.match).exists())

    def test_name_fallback_when_code_differs(self):
        # API uses a different code but the English name still matches.
        self._run({"matches": [api_match("MXX", "ZZZ", 1, 0,
                                          home_name="Mexico", away_name="South Africa")]})
        self.match.refresh_from_db()
        self.assertEqual((self.match.home_score, self.match.away_score), (1, 0))

    def test_unmatched_result_is_skipped(self):
        self._run({"matches": [api_match("BRA", "ARG", 4, 0)]})  # not in local schedule
        self.match.refresh_from_db()
        self.assertIsNone(self.match.home_score)  # nothing applied, no crash

    def test_out_of_window_result_is_not_applied(self):
        # Same teams, but a date years away (another season/source) — must not apply.
        self._run({"matches": [api_match("MEX", "RSA", 5, 0, utc="2030-01-01T00:00:00Z")]})
        self.match.refresh_from_db()
        self.assertIsNone(self.match.home_score)

    def test_inplay_and_unscored_results_are_ignored(self):
        self._run({"matches": [
            api_match("MEX", "RSA", 1, 1, status="IN_PLAY"),   # not finished
            api_match("MEX", "RSA", None, None),               # finished but no score
        ]})
        self.match.refresh_from_db()
        self.assertIsNone(self.match.home_score)

    def test_missing_token_errors(self):
        with self.assertRaises(CommandError):
            call_command("sync_results", token="", verbosity=0)

    def test_unknown_competition_errors(self):
        with self.assertRaises(CommandError):
            with mock.patch(FETCH, return_value={"matches": []}):
                call_command("sync_results", token="t", competition="nope", verbosity=0)
