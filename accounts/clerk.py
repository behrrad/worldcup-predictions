"""
Clerk integration helpers.

The browser runs Clerk's JS SDK and obtains a short-lived session JWT. We verify
that JWT here against Clerk's JWKS (public keys), then map the Clerk user to a
local Django user. Email/name come from the token claims when present, otherwise
we fetch them from Clerk's Backend API using the secret key.
"""
import json
import urllib.error
import urllib.request
from functools import lru_cache

import jwt
from django.conf import settings
from jwt import PyJWKClient

from .models import User


class ClerkError(Exception):
    pass


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    if not settings.CLERK_JWKS_URL:
        raise ClerkError("CLERK_JWKS_URL is not configured.")
    return PyJWKClient(settings.CLERK_JWKS_URL)


def verify_session_token(token: str) -> dict:
    """Verify a Clerk session JWT and return its claims, or raise ClerkError."""
    if not token:
        raise ClerkError("Missing session token.")
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.CLERK_FRONTEND_API_URL or None,
            options={"verify_aud": False},
            leeway=30,  # tolerate small clock skew
        )
    except Exception as exc:  # noqa: BLE001 - normalise all JWT errors
        raise ClerkError(str(exc)) from exc


def _fetch_clerk_user(clerk_user_id: str) -> dict:
    """Fetch a user record from Clerk's Backend API (needs the secret key)."""
    url = f"{settings.CLERK_BACKEND_API_URL}/users/{clerk_user_id}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {settings.CLERK_SECRET_KEY}",
            # A real User-Agent is required; Clerk's CDN blocks the default
            # "Python-urllib" agent with a 403.
            "User-Agent": "worldcup-predictions/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode())
    except urllib.error.URLError as exc:
        raise ClerkError(f"Clerk API error: {exc}") from exc


def _primary_email(data: dict) -> str:
    primary_id = data.get("primary_email_address_id")
    addresses = data.get("email_addresses", [])
    for address in addresses:
        if address.get("id") == primary_id:
            return address.get("email_address", "")
    return addresses[0]["email_address"] if addresses else ""


def get_or_create_user(claims: dict) -> User:
    """Map verified Clerk claims to a local user (creating one if needed)."""
    clerk_id = claims.get("sub")
    if not clerk_id:
        raise ClerkError("Token has no subject.")

    email = claims.get("email") or ""
    name = claims.get("name") or ""

    if not email:
        data = _fetch_clerk_user(clerk_id)
        email = _primary_email(data)
        name = " ".join(
            part for part in [data.get("first_name"), data.get("last_name")] if part
        ).strip()

    user, created = User.objects.get_or_create(
        clerk_id=clerk_id,
        defaults={"email": email or f"{clerk_id}@users.noreply.clerk",
                  "display_name": name},
    )

    changed = False
    if email and user.email != email:
        user.email = email
        changed = True
    if name and user.display_name != name:
        user.display_name = name
        changed = True
    if created:
        user.set_unusable_password()  # auth is handled entirely by Clerk
        changed = True
    if changed:
        user.save()
    return user
