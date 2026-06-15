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
