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


FINALIZE_FETCH = "predictions.results_sync.fetch_matches"
TOKEN_ENV = {consts.FOOTBALL_DATA_TOKEN_ENV: "t"}


class FinalizeIfDueTests(TestCase):
    """Lazy results finalization triggered from the live endpoint (no cron)."""

    def setUp(self):
        import os  # noqa: F401  (used via mock.patch.dict target)
        from predictions import seed_data as sd
        self.comp = make_competition(name="جام جهانی ۲۰۲۶", slug=sd.WC2026_SLUG)
        self.home = make_team(self.comp, name="مکزیک", code="MEX", name_en="Mexico")
        self.away = make_team(self.comp, name="آفریقای جنوبی", code="RSA", name_en="South Africa")
        self.kickoff = datetime(2026, 6, 11, 19, 0, tzinfo=utc_tz.utc)
        self.match = make_match(
            self.comp, home=self.home, away=self.away, match_number=1,
            kickoff=self.kickoff,
        )
        self.user = make_user()
        self.league = League.objects.create(name="L", competition=self.comp, owner=self.user)
        self.mem = Membership.objects.create(
            league=self.league, user=self.user, role=consts.Role.OWNER
        )
        Prediction.objects.create(
            membership=self.mem, match=self.match, predicted_home=2, predicted_away=1
        )

    def _ft(self):
        """Provider reported full time, official result still missing."""
        from predictions.models import Match
        Match.objects.filter(pk=self.match.pk).update(
            live_status=consts.LiveStatus.FULL_TIME,
            live_home_score=2, live_away_score=1,
        )

    def _run(self, now, payload=None):
        import os
        from unittest import mock as m
        from predictions import results_sync
        payload = payload if payload is not None else {
            "matches": [api_match("MEX", "RSA", 2, 1)]
        }
        with m.patch.dict(os.environ, TOKEN_ENV):
            with m.patch(FINALIZE_FETCH, return_value=payload) as fetch:
                ran = results_sync.finalize_if_due(self.comp, now=now)
        return ran, fetch

    def test_finalizes_after_full_time_and_recomputes(self):
        self._ft()
        now = self.kickoff + timedelta(hours=2)
        ran, fetch = self._run(now)
        self.assertTrue(ran)
        fetch.assert_called_once()
        self.match.refresh_from_db()
        self.assertTrue(self.match.is_finished)
        self.assertEqual((self.match.home_score, self.match.away_score), (2, 1))
        score = MatchScore.objects.get(membership=self.mem, match=self.match)
        self.assertEqual(score.tier, consts.Tier.EXACT)
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.results_checked_at, now)

    def test_claim_blocks_repeat_inside_window(self):
        self._ft()
        now = self.kickoff + timedelta(hours=2)
        # First caller fetches nothing useful; the match stays pending...
        ran, _ = self._run(now, payload={"matches": []})
        self.assertTrue(ran)
        # ...but a second caller within the claim window must not refetch.
        ran, fetch = self._run(now + timedelta(seconds=consts.RESULTS_SYNC_SECONDS - 5))
        self.assertFalse(ran)
        fetch.assert_not_called()
        # After the window it tries again.
        ran, _ = self._run(now + timedelta(seconds=consts.RESULTS_SYNC_SECONDS + 5))
        self.assertTrue(ran)

    def test_kickoff_age_triggers_without_live_signal(self):
        # The live feed never reported FT, but the match started 3 hours ago.
        ran, fetch = self._run(self.kickoff + timedelta(hours=3))
        self.assertTrue(ran)
        fetch.assert_called_once()

    def test_no_pending_match_is_a_cheap_noop(self):
        # Kickoff in the near past but inside the "could still be playing"
        # grace, no FT signal: nothing pending, no claim, no fetch.
        ran, fetch = self._run(self.kickoff + timedelta(hours=1))
        self.assertFalse(ran)
        fetch.assert_not_called()
        self.comp.refresh_from_db()
        self.assertIsNone(self.comp.results_checked_at)

    def test_old_unresolved_match_stops_being_chased(self):
        ran, fetch = self._run(
            self.kickoff + timedelta(hours=consts.RESULTS_PENDING_MAX_HOURS + 1)
        )
        self.assertFalse(ran)
        fetch.assert_not_called()

    def test_without_token_is_a_noop(self):
        import os
        from unittest import mock as m
        from predictions import results_sync
        self._ft()
        env = {consts.FOOTBALL_DATA_TOKEN_ENV: ""}
        with m.patch.dict(os.environ, env):
            with m.patch(FINALIZE_FETCH) as fetch:
                ran = results_sync.finalize_if_due(
                    self.comp, now=self.kickoff + timedelta(hours=2)
                )
        self.assertFalse(ran)
        fetch.assert_not_called()

    def test_non_world_cup_competition_never_syncs(self):
        # The test cup reuses real team codes; applying WC results onto it
        # would finalize wrong matches.
        other = make_competition(name="جام تست لایو")
        team_a = make_team(other, code="MEX", name_en="Mexico")
        team_b = make_team(other, code="RSA", name_en="South Africa")
        pending = make_match(other, home=team_a, away=team_b, kickoff=self.kickoff)
        from predictions.models import Match
        Match.objects.filter(pk=pending.pk).update(
            live_status=consts.LiveStatus.FULL_TIME)
        import os
        from unittest import mock as m
        from predictions import results_sync
        with m.patch.dict(os.environ, TOKEN_ENV):
            with m.patch(FINALIZE_FETCH) as fetch:
                ran = results_sync.finalize_if_due(
                    other, now=self.kickoff + timedelta(hours=2)
                )
        self.assertFalse(ran)
        fetch.assert_not_called()

    def test_fetch_failure_degrades_quietly(self):
        import os
        from unittest import mock as m
        from predictions import results_sync
        self._ft()
        with m.patch.dict(os.environ, TOKEN_ENV):
            with m.patch(FINALIZE_FETCH,
                         side_effect=results_sync.ResultsFetchError("down")):
                ran = results_sync.finalize_if_due(
                    self.comp, now=self.kickoff + timedelta(hours=2)
                )
        self.assertFalse(ran)
        self.match.refresh_from_db()
        self.assertFalse(self.match.is_finished)
