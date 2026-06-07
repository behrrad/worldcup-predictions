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
