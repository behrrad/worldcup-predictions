"""
Test settings — fast, isolated, no external services.

Run with:  python manage.py test --settings=config.settings_test
"""
from .settings import *  # noqa: F401,F403

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

# A non-"insecure" key so the production SECRET_KEY guard in settings.py is
# satisfied under DEBUG=False (this value is never used outside tests).
SECRET_KEY = "test-only-secret-key-not-used-anywhere-in-production-0123456789"

# Don't redirect http->https in the test client.
SECURE_SSL_REDIRECT = False

# Disable throttling for the general suite (a dedicated test re-enables it via
# override_settings). Keeping the scope keys with None rates avoids DRF's
# "no rate configured" error on the scoped throttles.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405  (imported via `from .settings import *`)
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {k: None for k in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]},  # noqa: F405
}
