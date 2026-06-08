"""
Django settings for the World Cup prediction league (پیش‌بینی جام جهانی).
"""

from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv
import os

from predictions import consts

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from a .env file if present.
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


# Known dev/placeholder SECRET_KEY values that must never sign sessions in
# production: Django's auto-generated dev default and the .env.example placeholder.
INSECURE_SECRET_KEYS = {"change-me-to-a-long-random-string"}


def is_insecure_secret_key(key: str) -> bool:
    return key.startswith("django-insecure-") or key in INSECURE_SECRET_KEYS


# --------------------------------------------------------------------------- #
# Core
# --------------------------------------------------------------------------- #
SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-dev-only-change-me-in-production-0a1b2c3d4e5f6g7h8i9j",
)

DEBUG = env_bool("DEBUG", True)

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0").split(",")
    if h.strip()
]

# Render injects the public hostname here; trust it automatically so we don't
# have to hardcode the *.onrender.com URL before the service exists.
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    CSRF_TRUSTED_ORIGINS_DEFAULT = f"https://{RENDER_EXTERNAL_HOSTNAME}"
else:
    CSRF_TRUSTED_ORIGINS_DEFAULT = ""

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CSRF_TRUSTED_ORIGINS", CSRF_TRUSTED_ORIGINS_DEFAULT
    ).split(",")
    if o.strip()
]


# --------------------------------------------------------------------------- #
# Applications
# --------------------------------------------------------------------------- #
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "corsheaders",
    # Local apps
    "accounts",
    "predictions",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves the Django admin's static files in production (no CDN
    # needed). Must sit right after SecurityMiddleware.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --------------------------------------------------------------------------- #
# Database (PostgreSQL)
# --------------------------------------------------------------------------- #
# Reads DATABASE_URL from the environment, e.g.
#   postgres://worldcup:worldcup@localhost:5432/worldcup
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ.get(
            "DATABASE_URL",
            "postgres://worldcup:worldcup@localhost:5432/worldcup",
        ),
        conn_max_age=600,
        # Supabase requires TLS. Enabled whenever we're not in local DEBUG.
        ssl_require=not DEBUG,
    )
}


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
AUTH_USER_MODEL = "accounts.User"

# Accounts allowed into the in-app admin (manual result entry). Django staff and
# superusers always qualify; this env var pins extra emails without a code change.
ADMIN_EMAILS = [
    e.strip().lower()
    for e in os.environ.get("ADMIN_EMAILS", "").split(",")
    if e.strip()
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 6},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

# --------------------------------------------------------------------------- #
# Clerk authentication
# --------------------------------------------------------------------------- #
CLERK_PUBLISHABLE_KEY = os.environ.get("CLERK_PUBLISHABLE_KEY", "")
CLERK_SECRET_KEY = os.environ.get("CLERK_SECRET_KEY", "")
CLERK_FRONTEND_API_URL = os.environ.get("CLERK_FRONTEND_API_URL", "").rstrip("/")
CLERK_JWKS_URL = os.environ.get("CLERK_JWKS_URL", "") or (
    f"{CLERK_FRONTEND_API_URL}/.well-known/jwks.json" if CLERK_FRONTEND_API_URL else ""
)
# Clerk-hosted JS bundle (served from the instance's Frontend API).
CLERK_JS_URL = (
    f"{CLERK_FRONTEND_API_URL}/npm/@clerk/clerk-js@5/dist/clerk.browser.js"
    if CLERK_FRONTEND_API_URL else ""
)
CLERK_BACKEND_API_URL = "https://api.clerk.com/v1"


# --------------------------------------------------------------------------- #
# REST framework + CORS (for the Next.js frontend)
# --------------------------------------------------------------------------- #
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "accounts.authentication.ClerkAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "UNAUTHENTICATED_USER": None,
    # Every endpoint requires authentication, so DRF rejects anonymous requests at
    # the permission check (before throttling) — an AnonRateThrottle here would
    # never fire. We throttle per authenticated user instead, with tighter scoped
    # limits on abuse-prone writes (predictions/throttles.py). Raw unauthenticated
    # floods are a host/edge concern (Render/CDN rate limiting).
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        consts.THROTTLE_SCOPE_USER: os.environ.get("THROTTLE_RATE_USER", consts.THROTTLE_RATE_USER),
        consts.THROTTLE_SCOPE_PREDICT: os.environ.get("THROTTLE_RATE_PREDICT", consts.THROTTLE_RATE_PREDICT),
        consts.THROTTLE_SCOPE_JOIN: os.environ.get("THROTTLE_RATE_JOIN", consts.THROTTLE_RATE_JOIN),
    },
}

CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ALLOWED_ORIGINS", "http://localhost:3077,http://127.0.0.1:3077"
    ).split(",")
    if o.strip()
]
CORS_ALLOW_CREDENTIALS = True

# Base URL of the Next.js frontend (the user-facing UI). Used to build
# absolute links back into the app — e.g. the admin "View on site" button for a
# League points at its real page at FRONTEND_URL/l/<slug>.
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3077").rstrip("/")


# --------------------------------------------------------------------------- #
# Internationalization — Persian / RTL
# --------------------------------------------------------------------------- #
LANGUAGE_CODE = "fa-ir"

TIME_ZONE = os.environ.get("TIME_ZONE", "Asia/Tehran")

USE_I18N = True

USE_TZ = True


# --------------------------------------------------------------------------- #
# Static files
# --------------------------------------------------------------------------- #
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# WhiteNoise: compress + hash static files so the admin panel works in prod.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Production-leaning security toggles (enabled automatically when DEBUG is off).
if not DEBUG:
    # Refuse to boot in production with a known/placeholder SECRET_KEY — a strong
    # key MUST come from the environment / secret manager.
    if is_insecure_secret_key(SECRET_KEY):
        raise ImproperlyConfigured(
            "Set a strong, unique SECRET_KEY environment variable in production "
            "(a known development/placeholder value is still in use)."
        )

    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_CONTENT_TYPE_NOSNIFF = True

    # HTTP Strict Transport Security. Defaults to 1 year; set SECURE_HSTS_SECONDS=0
    # to disable while validating TLS on a new domain.
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", 31536000))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
    SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", True)
