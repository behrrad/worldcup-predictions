"""
Tests for the Telegram reminder feature (predictions/telegram.py + endpoints).

No real network: the send / getUpdates seams (``telegram.send_message`` and
``telegram._get_updates``) are patched, and the bot token is configured per-test
via override_settings only where the code path needs it.
"""
from datetime import datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from predictions import consts, telegram
from predictions.models import NotificationLog, Prediction, TelegramState

from .factories import join, make_competition, make_league, make_match, make_user

TEHRAN = ZoneInfo("Asia/Tehran")


def _start_update(update_id, chat_id, text):
    return {
        "update_id": update_id,
        "message": {
            "chat": {"id": chat_id, "type": consts.TELEGRAM_CHAT_TYPE_PRIVATE},
            "text": text,
            "from": {"id": chat_id, "username": "tester"},
        },
    }


def _linked(chat_id, **kw):
    user = make_user(**kw)
    user.telegram_chat_id = chat_id
    user.save()
    return user


# --------------------------------------------------------------------------- #
# Linking
# --------------------------------------------------------------------------- #
class LinkingTests(TestCase):
    def test_link_token_is_reused_until_expiry(self):
        user = make_user()
        first = telegram.link_token_for(user)
        user.refresh_from_db()
        self.assertEqual(first, telegram.link_token_for(user))

    def test_start_links_account_and_replies(self):
        user = make_user()
        token = telegram.link_token_for(user)
        with mock.patch.object(telegram, "send_message", return_value=True) as sm:
            telegram.process_update(_start_update(1, 909, f"/start {token}"))
        user.refresh_from_db()
        self.assertEqual(user.telegram_chat_id, 909)
        self.assertEqual(user.telegram_link_token, "")  # token burned
        self.assertIn(consts.TG_REPLY_LINKED.split("{")[0], sm.call_args[0][1])

    def test_start_with_invalid_token_does_not_link(self):
        with mock.patch.object(telegram, "send_message", return_value=True) as sm:
            telegram.process_update(_start_update(1, 42, "/start nope"))
        self.assertFalse(User.objects.filter(telegram_chat_id=42).exists())
        self.assertEqual(sm.call_args[0][1], consts.TG_REPLY_LINK_INVALID)

    def test_start_without_payload_explains(self):
        with mock.patch.object(telegram, "send_message", return_value=True) as sm:
            telegram.process_update(_start_update(1, 42, "/start"))
        self.assertEqual(sm.call_args[0][1], consts.TG_REPLY_START_NO_TOKEN)

    def test_expired_token_rejected(self):
        user = make_user()
        token = telegram.link_token_for(user)
        User.objects.filter(pk=user.pk).update(
            telegram_link_token_at=timezone.now()
            - timedelta(seconds=consts.TELEGRAM_LINK_TOKEN_MAX_AGE_SECONDS + 10)
        )
        self.assertIsNone(telegram.link_account(token, 1))

    def test_relink_moves_chat_id_off_old_account(self):
        old = _linked(100)
        new = make_user()
        token = telegram.link_token_for(new)
        linked = telegram.link_account(token, 100)
        old.refresh_from_db()
        new.refresh_from_db()
        self.assertEqual(linked.pk, new.pk)
        self.assertIsNone(old.telegram_chat_id)
        self.assertEqual(new.telegram_chat_id, 100)

    def test_stop_disables_notifications(self):
        user = _linked(7)
        with mock.patch.object(telegram, "send_message", return_value=True):
            telegram.process_update(_start_update(1, 7, consts.TELEGRAM_STOP_COMMAND))
        user.refresh_from_db()
        self.assertFalse(user.telegram_notify)

    def test_group_chat_is_ignored(self):
        update = {
            "update_id": 1,
            "message": {"chat": {"id": -10, "type": "group"}, "text": "/start x"},
        }
        with mock.patch.object(telegram, "send_message", return_value=True) as sm:
            telegram.process_update(update)
        sm.assert_not_called()

    @override_settings(TELEGRAM_BOT_TOKEN="t", TELEGRAM_BOT_USERNAME="@mybot")
    def test_deep_link_built(self):
        link = telegram.deep_link(make_user())
        self.assertTrue(link.startswith("https://t.me/mybot?start="))

    def test_deep_link_none_when_unconfigured(self):
        self.assertIsNone(telegram.deep_link(make_user()))


# --------------------------------------------------------------------------- #
# Polling (getUpdates drain + atomic claim)
# --------------------------------------------------------------------------- #
class PollingTests(TestCase):
    def test_noop_without_token(self):
        self.assertEqual(telegram.poll_updates(), 0)

    @override_settings(TELEGRAM_BOT_TOKEN="t")
    def test_poll_processes_and_advances_offset(self):
        user = make_user()
        token = telegram.link_token_for(user)
        payload = {"ok": True, "result": [_start_update(10, 999, f"/start {token}")]}
        with mock.patch.object(telegram, "_get_updates", return_value=payload), \
                mock.patch.object(telegram, "send_message", return_value=True):
            processed = telegram.poll_updates(timezone.now())
        self.assertEqual(processed, 1)
        user.refresh_from_db()
        self.assertEqual(user.telegram_chat_id, 999)
        self.assertEqual(TelegramState.objects.get(pk=1).update_offset, 11)

    @override_settings(TELEGRAM_BOT_TOKEN="t")
    def test_claim_blocks_second_poll_in_window(self):
        now = timezone.now()
        with mock.patch.object(telegram, "_get_updates",
                               return_value={"ok": True, "result": []}) as gu:
            telegram.poll_updates(now)
            telegram.poll_updates(now)  # within TELEGRAM_POLL_SECONDS -> claim denied
        self.assertEqual(gu.call_count, 1)


# --------------------------------------------------------------------------- #
# Who still owes a prediction (digest + nudge eligibility)
# --------------------------------------------------------------------------- #
class DueTests(TestCase):
    def setUp(self):
        self.comp = make_competition()
        self.league = make_league(self.comp)
        self.user = _linked(11)
        self.membership = join(self.league, self.user)

    def test_nudge_for_unpredicted_imminent_match(self):
        now = timezone.now()
        match = make_match(self.comp, kickoff=now + timedelta(minutes=20))
        due = telegram.due_nudges(now)
        self.assertEqual([(u.pk, [m.pk for m in ms]) for u, ms in due],
                         [(self.user.pk, [match.pk])])

    def test_no_nudge_once_predicted(self):
        now = timezone.now()
        match = make_match(self.comp, kickoff=now + timedelta(minutes=20))
        Prediction.objects.create(
            membership=self.membership, match=match, predicted_home=1, predicted_away=0,
        )
        self.assertEqual(telegram.due_nudges(now), [])

    def test_no_nudge_when_notify_off(self):
        now = timezone.now()
        make_match(self.comp, kickoff=now + timedelta(minutes=20))
        self.user.telegram_notify = False
        self.user.save()
        self.assertEqual(telegram.due_nudges(now), [])

    def test_no_nudge_when_unlinked(self):
        now = timezone.now()
        make_match(self.comp, kickoff=now + timedelta(minutes=20))
        self.user.telegram_chat_id = None
        self.user.save()
        self.assertEqual(telegram.due_nudges(now), [])

    def test_match_outside_window_not_nudged(self):
        now = timezone.now()
        make_match(self.comp, kickoff=now + timedelta(hours=3))
        self.assertEqual(telegram.due_nudges(now), [])

    def test_digest_respects_morning_hour(self):
        make_match(self.comp, kickoff=datetime(2026, 6, 14, 15, 0, tzinfo=TEHRAN))
        early = datetime(2026, 6, 14, 7, 0, tzinfo=TEHRAN)
        self.assertEqual(telegram.due_digests(early), [])
        late = datetime(2026, 6, 14, 10, 0, tzinfo=TEHRAN)
        self.assertEqual([u.pk for u, _ in telegram.due_digests(late)], [self.user.pk])


# --------------------------------------------------------------------------- #
# Sending (dedup + rollback)
# --------------------------------------------------------------------------- #
class RunNotificationsTests(TestCase):
    def setUp(self):
        self.comp = make_competition()
        self.league = make_league(self.comp)
        self.user = _linked(33)
        self.membership = join(self.league, self.user)

    def test_digest_sent_once_per_day(self):
        # 10:00 Tehran, a match later today, far enough out that no nudge fires.
        now = datetime(2026, 6, 14, 10, 0, tzinfo=TEHRAN)
        make_match(self.comp, kickoff=datetime(2026, 6, 14, 15, 0, tzinfo=TEHRAN))
        with mock.patch.object(telegram, "send_message", return_value=True) as sm:
            self.assertEqual(telegram.run_notifications(now)["digests"], 1)
            self.assertEqual(telegram.run_notifications(now)["digests"], 0)
        self.assertEqual(sm.call_count, 1)
        self.assertEqual(
            NotificationLog.objects.filter(kind=consts.NotifyKind.DIGEST).count(), 1,
        )

    def test_failed_send_is_rolled_back(self):
        now = timezone.now()
        make_match(self.comp, kickoff=now + timedelta(minutes=20))
        with mock.patch.object(telegram, "send_message", return_value=False):
            self.assertEqual(telegram.run_notifications(now)["nudges"], 0)
        # Nothing logged, so the next tick retries.
        self.assertEqual(NotificationLog.objects.count(), 0)

    def test_nudge_logged_per_match(self):
        now = timezone.now()
        match = make_match(self.comp, kickoff=now + timedelta(minutes=20))
        with mock.patch.object(telegram, "send_message", return_value=True):
            telegram.run_notifications(now)
        self.assertTrue(NotificationLog.objects.filter(
            user=self.user, kind=consts.NotifyKind.NUDGE, dedup_key=str(match.id),
        ).exists())

    def test_management_command_runs(self):
        call_command("send_telegram_notifications")  # no token -> no-op, no error


# --------------------------------------------------------------------------- #
# Live match events (kickoff / goal / half-time / full-time)
# --------------------------------------------------------------------------- #
def _match_recipient(chat_id, **kw):
    user = _linked(chat_id, **kw)
    user.telegram_notify_matches = True
    user.save()
    return user


def _set_live(match, status, home=None, away=None, minute=""):
    """Write live_* fields the way live.py does (queryset.update, never save)."""
    from predictions.models import Match

    Match.objects.filter(pk=match.pk).update(
        live_status=status, live_home_score=home, live_away_score=away,
        live_minute=minute, live_updated_at=timezone.now(),
    )


class MatchEventTests(TestCase):
    def setUp(self):
        self.comp = make_competition()
        self.league = make_league(self.comp)
        self.user = _match_recipient(55)
        self.membership = join(self.league, self.user)

    def _predict(self, match, home, away, membership=None):
        return Prediction.objects.create(
            membership=membership or self.membership, match=match,
            predicted_home=home, predicted_away=away,
        )

    def _texts(self, now):
        with mock.patch.object(telegram, "send_message", return_value=True) as sm:
            sent = telegram.run_match_events(now)
        return sent, [c.args[1] for c in sm.call_args_list]

    def test_kickoff_fires_once_with_pick(self):
        now = timezone.now()
        match = make_match(self.comp, kickoff=now - timedelta(minutes=5))
        self._predict(match, 2, 1)
        sent, texts = self._texts(now)
        self.assertEqual(sent["events"], 1)
        self.assertTrue(any(consts.TG_EVENT_KICKOFF_TITLE in t for t in texts))
        self.assertTrue(any("۲-۱" in t for t in texts))  # the pick, Persian digits
        # A second tick sends nothing new.
        self.assertEqual(self._texts(now)[0]["events"], 0)
        self.assertEqual(NotificationLog.objects.filter(
            kind=consts.NotifyKind.KICKOFF, dedup_key=str(match.id)).count(), 1)

    def test_goal_shows_on_track_when_score_matches_pick(self):
        now = timezone.now()
        match = make_match(self.comp, kickoff=now - timedelta(minutes=20))
        self._predict(match, 1, 0)
        _set_live(match, consts.LiveStatus.LIVE, home=1, away=0, minute="35")
        _, texts = self._texts(now)
        goal = next(t for t in texts if consts.TG_EVENT_GOAL_TITLE.split("{")[0] in t)
        self.assertIn(consts.TG_EVENT_ON_TRACK, goal)
        self.assertIn("۳۵", goal)  # the live minute

    def test_goal_dedup_is_per_scoreline(self):
        now = timezone.now()
        match = make_match(self.comp, kickoff=now - timedelta(minutes=20))
        _set_live(match, consts.LiveStatus.LIVE, home=1, away=0)
        self._texts(now)
        _set_live(match, consts.LiveStatus.LIVE, home=2, away=1)
        self._texts(now)
        self.assertEqual(
            NotificationLog.objects.filter(kind=consts.NotifyKind.GOAL).count(), 2)
        # Re-observing 2-1 sends no new goal.
        self.assertEqual(self._texts(now)[0]["events"], 0)

    def test_halftime_event_logged(self):
        now = timezone.now()
        match = make_match(self.comp, kickoff=now - timedelta(minutes=50))
        _set_live(match, consts.LiveStatus.HALFTIME, home=0, away=0)
        self._texts(now)
        self.assertTrue(NotificationLog.objects.filter(
            kind=consts.NotifyKind.HALFTIME, dedup_key=str(match.id)).exists())

    def test_second_half_fires_when_clock_resumes(self):
        now = timezone.now()
        match = make_match(self.comp, kickoff=now - timedelta(hours=1))
        self._predict(match, 1, 0)
        _set_live(match, consts.LiveStatus.LIVE, home=1, away=0, minute="47")
        _, texts = self._texts(now)
        self.assertTrue(any(consts.TG_EVENT_SECONDHALF_TITLE in t for t in texts))
        self.assertTrue(NotificationLog.objects.filter(
            kind=consts.NotifyKind.SECOND_HALF, dedup_key=str(match.id)).exists())
        # Fires once: a later second-half tick adds nothing new for this kind.
        _set_live(match, consts.LiveStatus.LIVE, home=1, away=0, minute="55")
        self._texts(now)
        self.assertEqual(NotificationLog.objects.filter(
            kind=consts.NotifyKind.SECOND_HALF, dedup_key=str(match.id)).count(), 1)

    def test_no_second_half_during_first_half(self):
        now = timezone.now()
        match = make_match(self.comp, kickoff=now - timedelta(minutes=30))
        _set_live(match, consts.LiveStatus.LIVE, home=0, away=0, minute="30")
        self._texts(now)
        self.assertFalse(
            NotificationLog.objects.filter(kind=consts.NotifyKind.SECOND_HALF).exists())

    def test_no_stale_second_half_deep_in_the_half(self):
        now = timezone.now()
        match = make_match(self.comp, kickoff=now - timedelta(hours=1))
        _set_live(match, consts.LiveStatus.LIVE, home=1, away=1, minute="75")
        self._texts(now)
        self.assertFalse(
            NotificationLog.objects.filter(kind=consts.NotifyKind.SECOND_HALF).exists())

    def test_fulltime_official_includes_points(self):
        now = timezone.now()
        match = make_match(self.comp, kickoff=now - timedelta(hours=2))
        self._predict(match, 2, 1)
        match.home_score, match.away_score = 2, 1
        match.save()  # official result -> FINISHED, scores recomputed
        sent, texts = self._texts(now)
        ft = next(t for t in texts if consts.TG_EVENT_FULLTIME_TITLE in t)
        self.assertIn(consts.TG_EVENT_POINTS.split("{")[0], ft)  # earned points line
        # Only full-time fires (kickoff is suppressed once the match is over).
        self.assertEqual(sent["events"], 1)

    def test_fulltime_live_fallback_when_no_official_result(self):
        now = timezone.now()
        match = make_match(self.comp, kickoff=now - timedelta(hours=1))
        self._predict(match, 2, 1)  # exact, scored off the live final
        _set_live(match, consts.LiveStatus.FULL_TIME, home=2, away=1)
        _, texts = self._texts(now)
        ft = next(t for t in texts if consts.TG_EVENT_FULLTIME_TITLE in t)
        self.assertIn("۲ - ۱", ft)
        self.assertIn(consts.TG_EVENT_POINTS.split("{")[0], ft)

    def test_fulltime_zero_points_message(self):
        now = timezone.now()
        self.league.points_participation = 0  # a wrong pick is worth nothing here
        self.league.save()
        match = make_match(self.comp, kickoff=now - timedelta(hours=1))
        self._predict(match, 0, 0)  # wrong outcome vs a 2-1 result
        _set_live(match, consts.LiveStatus.FULL_TIME, home=2, away=1)
        _, texts = self._texts(now)
        ft = next(t for t in texts if consts.TG_EVENT_FULLTIME_TITLE in t)
        self.assertIn(consts.TG_EVENT_POINTS_NONE, ft)

    def test_fulltime_no_pick_message(self):
        now = timezone.now()
        match = make_match(self.comp, kickoff=now - timedelta(hours=1))
        _set_live(match, consts.LiveStatus.FULL_TIME, home=1, away=0)
        _, texts = self._texts(now)
        ft = next(t for t in texts if consts.TG_EVENT_FULLTIME_TITLE in t)
        self.assertIn(consts.TG_EVENT_NO_PICK, ft)

    def test_no_events_without_optin(self):
        now = timezone.now()
        self.user.telegram_notify_matches = False
        self.user.save()
        make_match(self.comp, kickoff=now - timedelta(minutes=5))
        self.assertEqual(self._texts(now)[0]["events"], 0)

    def test_no_events_when_unlinked(self):
        now = timezone.now()
        self.user.telegram_chat_id = None
        self.user.save()
        make_match(self.comp, kickoff=now - timedelta(minutes=5))
        self.assertEqual(self._texts(now)[0]["events"], 0)

    def test_old_match_outside_window(self):
        now = timezone.now()
        match = make_match(self.comp, kickoff=now - timedelta(hours=5))
        match.home_score, match.away_score = 1, 0
        match.save()
        self.assertEqual(self._texts(now)[0]["events"], 0)

    def test_failed_send_rolls_back_for_retry(self):
        now = timezone.now()
        make_match(self.comp, kickoff=now - timedelta(minutes=5))
        with mock.patch.object(telegram, "send_message", return_value=False):
            telegram.run_match_events(now)
        self.assertEqual(NotificationLog.objects.count(), 0)

    def test_no_stale_kickoff_for_match_already_underway(self):
        # Opting in / first seeing a match well after kickoff must not DM "kickoff!".
        now = timezone.now()
        make_match(self.comp, kickoff=now - timedelta(minutes=40))
        self.assertEqual(self._texts(now)[0]["events"], 0)
        self.assertFalse(
            NotificationLog.objects.filter(kind=consts.NotifyKind.KICKOFF).exists())

    def test_no_goal_event_at_halftime(self):
        now = timezone.now()
        match = make_match(self.comp, kickoff=now - timedelta(minutes=50))
        _set_live(match, consts.LiveStatus.HALFTIME, home=1, away=0)
        self._texts(now)
        self.assertFalse(
            NotificationLog.objects.filter(kind=consts.NotifyKind.GOAL).exists())
        self.assertTrue(
            NotificationLog.objects.filter(kind=consts.NotifyKind.HALFTIME).exists())

    def test_live_fulltime_without_scores_does_not_crash_or_fire(self):
        # A FULL_TIME live status with NULL scores (partial/stale row) must not
        # feed None into the scorer — it should simply not fire full-time yet.
        now = timezone.now()
        match = make_match(self.comp, kickoff=now - timedelta(hours=1))
        self._predict(match, 1, 0)
        _set_live(match, consts.LiveStatus.FULL_TIME, home=None, away=None)
        self.assertEqual(self._texts(now)[0]["events"], 0)
        self.assertFalse(
            NotificationLog.objects.filter(kind=consts.NotifyKind.FULLTIME).exists())

    def test_goal_minute_is_html_escaped(self):
        # The minute is provider-controlled; its "<" must be escaped before it
        # lands in the parse_mode=HTML message (the bold <b> tags are ours).
        title = telegram._event_title({"phase": consts.NotifyKind.GOAL, "minute": "45<b"})
        self.assertIn("&lt;", title)
        self.assertNotIn("۴۵<", title)  # the unescaped minute must not appear


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
class TelegramEndpointTests(TestCase):
    def setUp(self):
        self.user = make_user(email="tg@test.com")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @override_settings(TELEGRAM_BOT_TOKEN="t", TELEGRAM_BOT_USERNAME="mybot")
    def test_status_unlinked_returns_deep_link(self):
        with mock.patch.object(telegram, "poll_updates", return_value=0):
            res = self.client.get(reverse("api_me_telegram"))
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["configured"])
        self.assertFalse(body["linked"])
        self.assertTrue(body["deep_link"].startswith("https://t.me/mybot?start="))

    def test_patch_toggles_notify(self):
        res = self.client.patch(
            reverse("api_me_telegram"), {"notify": False}, format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.telegram_notify)

    def test_patch_toggles_notify_matches(self):
        self.assertTrue(self.user.telegram_notify_matches)  # on by default
        res = self.client.patch(
            reverse("api_me_telegram"), {"notify_matches": False}, format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.telegram_notify_matches)
        self.assertFalse(res.json()["notify_matches"])

    def test_patch_applies_both_toggles_in_one_request(self):
        res = self.client.patch(
            reverse("api_me_telegram"),
            {"notify": False, "notify_matches": True}, format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.telegram_notify)
        self.assertTrue(self.user.telegram_notify_matches)

    def test_patch_unlinks(self):
        self.user.telegram_chat_id = 99
        self.user.save()
        res = self.client.patch(
            reverse("api_me_telegram"), {"unlink": True}, format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.telegram_chat_id)

    def test_tick_forbidden_without_key(self):
        self.assertEqual(APIClient().post(reverse("api_task_tick")).status_code, 403)

    @override_settings(TASK_TRIGGER_KEY="secret")
    def test_tick_rejects_wrong_key(self):
        res = APIClient().post(reverse("api_task_tick"), HTTP_X_TASK_KEY="nope")
        self.assertEqual(res.status_code, 403)

    @override_settings(TASK_TRIGGER_KEY="secret")
    def test_tick_runs_with_correct_key(self):
        res = APIClient().post(reverse("api_task_tick"), HTTP_X_TASK_KEY="secret")
        self.assertEqual(res.status_code, 200)
        self.assertIn("digests", res.json())
