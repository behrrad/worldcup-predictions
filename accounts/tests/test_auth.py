from unittest import mock

from django.test import RequestFactory, TestCase
from rest_framework.exceptions import AuthenticationFailed

from accounts import clerk
from accounts.authentication import ClerkAuthentication
from accounts.models import User


class ClerkAuthenticationTests(TestCase):
    def setUp(self):
        self.auth = ClerkAuthentication()
        self.rf = RequestFactory()

    def test_no_header_returns_none(self):
        request = self.rf.get("/api/me/")
        self.assertIsNone(self.auth.authenticate(request))

    def test_non_bearer_returns_none(self):
        request = self.rf.get("/api/me/", HTTP_AUTHORIZATION="Basic abc")
        self.assertIsNone(self.auth.authenticate(request))

    @mock.patch("accounts.authentication.clerk.get_or_create_user")
    @mock.patch("accounts.authentication.clerk.verify_session_token")
    def test_valid_token_authenticates(self, verify, get_user):
        verify.return_value = {"sub": "user_1", "email": "x@test.com"}
        user = User.objects.create_user(email="x@test.com", password="pw")
        get_user.return_value = user

        request = self.rf.get("/api/me/", HTTP_AUTHORIZATION="Bearer good.token.here")
        result = self.auth.authenticate(request)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], user)
        verify.assert_called_once_with("good.token.here")

    @mock.patch("accounts.authentication.clerk.verify_session_token",
                side_effect=clerk.ClerkError("bad"))
    def test_invalid_token_raises(self, _verify):
        request = self.rf.get("/api/me/", HTTP_AUTHORIZATION="Bearer bad")
        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate(request)


class GetOrCreateUserTests(TestCase):
    @mock.patch("accounts.clerk._fetch_clerk_user")
    def test_email_from_claims_skips_api_call(self, fetch):
        user = clerk.get_or_create_user({
            "sub": "user_abc", "email": "claims@test.com", "name": "علی",
        })
        fetch.assert_not_called()
        self.assertEqual(user.clerk_id, "user_abc")
        self.assertEqual(user.email, "claims@test.com")
        self.assertEqual(user.display_name, "علی")

    @mock.patch("accounts.clerk._fetch_clerk_user")
    def test_fetches_from_api_when_no_email_claim(self, fetch):
        fetch.return_value = {
            "primary_email_address_id": "e1",
            "email_addresses": [{"id": "e1", "email_address": "api@test.com"}],
            "first_name": "رضا", "last_name": "محمدی",
        }
        user = clerk.get_or_create_user({"sub": "user_xyz"})
        fetch.assert_called_once_with("user_xyz")
        self.assertEqual(user.email, "api@test.com")
        self.assertEqual(user.display_name, "رضا محمدی")

    @mock.patch("accounts.clerk._fetch_clerk_user")
    def test_existing_user_is_updated(self, _fetch):
        User.objects.create_user(email="old@test.com", password="pw", clerk_id="user_1")
        user = clerk.get_or_create_user({"sub": "user_1", "email": "new@test.com"})
        self.assertEqual(user.email, "new@test.com")
        self.assertEqual(User.objects.filter(clerk_id="user_1").count(), 1)

    def test_missing_sub_raises(self):
        with self.assertRaises(clerk.ClerkError):
            clerk.get_or_create_user({})
