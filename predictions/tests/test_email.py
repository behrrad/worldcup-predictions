"""
Tests for the Resend email sender and the announcement broadcast
(predictions/email.py). No real network: the HTTP seam (email._post) is patched,
and the API key is configured per-test via override_settings only where a code
path needs it.
"""
from unittest import mock

from django.test import TestCase, override_settings

from predictions import consts, email
from predictions.models import NotificationLog

from .factories import join, make_competition, make_league, make_user


class IsRealAddressTests(TestCase):
    def test_placeholder_addresses_are_skipped(self):
        self.assertFalse(email.is_real_address("abc123@users.noreply.clerk"))
        self.assertFalse(email.is_real_address(""))
        self.assertTrue(email.is_real_address("real@example.com"))


class SendEmailTests(TestCase):
    def test_no_op_when_unconfigured(self):
        with mock.patch.object(email, "_post", return_value=True) as post:
            self.assertFalse(email.send_email("s", "b", "real@example.com"))
        self.assertEqual(post.call_count, 0)

    @override_settings(RESEND_API_KEY="k", DEFAULT_FROM_EMAIL="from@x.com")
    def test_sends_when_configured(self):
        with mock.patch.object(email, "_post", return_value=True) as post:
            self.assertTrue(email.send_email("s", "b", "real@example.com"))
        self.assertEqual(post.call_count, 1)
        payload = post.call_args[0][0]
        self.assertEqual(payload["to"], ["real@example.com"])
        self.assertEqual(payload["subject"], "s")

    @override_settings(RESEND_API_KEY="k")
    def test_placeholder_address_is_not_sent(self):
        with mock.patch.object(email, "_post", return_value=True) as post:
            self.assertFalse(email.send_email("s", "b", "x@users.noreply.clerk"))
        self.assertEqual(post.call_count, 0)


class BroadcastAnnouncementEmailTests(TestCase):
    def setUp(self):
        self.comp = make_competition()
        self.league = make_league(self.comp, owner=make_user(email="owner@x.com"))
        join(self.league, user=make_user(email="a@x.com"))
        join(self.league, user=make_user(email="b@x.com"))
        # A member with only a placeholder address is never emailed.
        join(self.league, user=make_user(email="ph@users.noreply.clerk"))
        self.key = consts.ANNOUNCE_2X_EMAIL_CAMPAIGN

    def test_recipients_exclude_placeholder_addresses(self):
        emails = {u.email for u in email.announcement_recipients()}
        self.assertEqual(emails, {"owner@x.com", "a@x.com", "b@x.com"})

    @override_settings(RESEND_API_KEY="k")
    def test_sends_once_per_real_recipient(self):
        with mock.patch.object(email, "_post", return_value=True) as post:
            sent = email.broadcast_announcement("s", "hi {name} {url}", self.key)
        self.assertEqual(sent, 3)
        self.assertEqual(post.call_count, 3)
        self.assertEqual(
            NotificationLog.objects.filter(kind=consts.NotifyKind.ANNOUNCE).count(), 3
        )

    @override_settings(RESEND_API_KEY="k")
    def test_is_idempotent_on_rerun(self):
        with mock.patch.object(email, "_post", return_value=True):
            email.broadcast_announcement("s", "hi {name} {url}", self.key)
        with mock.patch.object(email, "_post", return_value=True) as post2:
            again = email.broadcast_announcement("s", "hi {name} {url}", self.key)
        self.assertEqual(again, 0)
        self.assertEqual(post2.call_count, 0)

    def test_no_op_when_unconfigured(self):
        with mock.patch.object(email, "_post", return_value=True) as post:
            sent = email.broadcast_announcement("s", "hi {name} {url}", self.key)
        self.assertEqual(sent, 0)
        self.assertEqual(post.call_count, 0)
        self.assertEqual(NotificationLog.objects.count(), 0)
