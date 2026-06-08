from django.test import SimpleTestCase

from config.settings import is_insecure_secret_key


class SecretKeyGuardTests(SimpleTestCase):
    """The production guard must reject every known dev/placeholder SECRET_KEY."""

    def test_rejects_dev_default(self):
        self.assertTrue(is_insecure_secret_key("django-insecure-anything-here"))

    def test_rejects_env_example_placeholder(self):
        self.assertTrue(is_insecure_secret_key("change-me-to-a-long-random-string"))

    def test_allows_a_strong_unique_key(self):
        self.assertFalse(is_insecure_secret_key("Zq7-Real-Unique-9f8a7b6c5d4e3f2a1b0c-prod-key"))
