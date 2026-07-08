"""
Transactional / announcement email via Resend's HTTP API.

Mirrors the philosophy of ``predictions/telegram.py``: env-gated (no
``RESEND_API_KEY`` => every send is a silent no-op, so the feature ships dark),
self-contained, and posting with an explicit ``User-Agent`` (the default
``Python-urllib`` agent is blocked by many edge/CDN layers — the same lesson as
``accounts/clerk.py``).

Swapping providers later is a one-file change: replace ``_post`` here (or point
``settings`` at a different backend) — nothing else imports the HTTP details.
"""
import json
import urllib.error
import urllib.request

from django.conf import settings

from . import consts


def is_configured() -> bool:
    """True once a Resend API key is present; otherwise sends are no-ops."""
    return bool(getattr(settings, "RESEND_API_KEY", ""))


def _post(payload: dict) -> bool:
    """POST one email to Resend. Returns True on a 2xx, False on any error."""
    request = urllib.request.Request(
        consts.RESEND_API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": consts.EMAIL_USER_AGENT,
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=consts.EMAIL_FETCH_TIMEOUT) as response:
            return 200 <= response.status < 300
    except urllib.error.URLError:
        return False


def is_real_address(email: str) -> bool:
    """False for the placeholder addresses minted for users without a real email
    (see accounts/clerk.py) — we never mail those."""
    return bool(email) and not email.endswith(consts.EMAIL_PLACEHOLDER_SUFFIX)


def send_email(subject: str, body: str, to: str) -> bool:
    """Send a single plain-text email. No-op (returns False) when unconfigured
    or when `to` is a placeholder address."""
    if not is_configured() or not is_real_address(to):
        return False
    return _post({
        "from": settings.DEFAULT_FROM_EMAIL,
        "to": [to],
        "subject": subject,
        "text": body,
    })


def announcement_recipients():
    """Distinct active users who belong to at least one active-competition league
    and have a real (non-placeholder) email address."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    users = (
        User.objects.filter(
            is_active=True,
            memberships__league__competition__is_active=True,
        )
        .distinct()
    )
    return [u for u in users if is_real_address(u.email)]


def broadcast_announcement(subject: str, body_template: str, dedup_key: str) -> int:
    """Email `body_template` (formatted with {name} + {url}) once to every
    announcement recipient. Idempotent via the same NotificationLog guard as the
    Telegram broadcast (kind=ANNOUNCE, distinct dedup_key). No-op when unconfigured.
    Returns the number of members newly emailed."""
    from .models import NotificationLog

    if not is_configured():
        return 0
    url = f"{settings.FRONTEND_URL}{consts.TELEGRAM_REMINDER_PATH}"
    sent = 0
    for user in announcement_recipients():
        obj, created = NotificationLog.objects.get_or_create(
            user=user, kind=consts.NotifyKind.ANNOUNCE, dedup_key=dedup_key,
        )
        if not created:
            continue
        body = body_template.format(name=user.public_name, url=url)
        if send_email(subject, body, user.email):
            sent += 1
        else:
            obj.delete()  # let the next run retry
    return sent
