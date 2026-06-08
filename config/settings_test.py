"""
Test settings — fast, isolated, no external services.

Run with:  python manage.py test --settings=config.settings_test
"""
import os

# Force a strong SECRET_KEY into the environment BEFORE importing base settings,
# so the production SECRET_KEY guard there can't raise ImproperlyConfigured during
# import in a DEBUG=False / unset-key environment (e.g. CI). This value is only
# ever used by the test suite.
os.environ["SECRET_KEY"] = "test-only-secret-key-not-used-anywhere-in-production-0123456789"

from .settings import *  # noqa: E402,F401,F403

# In-memory SQLite: fast and requires no running Postgres/Supabase.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Dummy Clerk config so nothing tries to hit the network during tests.
CLERK_PUBLISHABLE_KEY = "pk_test_dummy"
CLERK_SECRET_KEY = "sk_test_dummy"
CLERK_FRONTEND_API_URL = "https://example.clerk.accounts.dev"
CLERK_JWKS_URL = "https://example.clerk.accounts.dev/.well-known/jwks.json"

# Faster password hashing in tests.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Keep things deterministic.
DEBUG = False

# Don't redirect http->https in the test client.
SECURE_SSL_REDIRECT = False

# Disable throttling for the general suite (a dedicated test re-enables it via
# patching). Keeping the scope keys with None rates avoids DRF's
# "no rate configured" error on the scoped throttles.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405  (imported via `from .settings import *`)
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {k: None for k in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]},  # noqa: F405
}
