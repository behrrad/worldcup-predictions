"""
Telegram reminders.

A bot DMs members who haven't predicted a match yet — a once-a-day morning
digest of the day's still-open matches, plus a final nudge shortly before
kickoff. Linking is one-tap: the website hands out a deep link carrying a short
single-use token; tapping **Start** in the bot sends ``/start <token>``, which
we resolve to the user and store their chat id.

Design mirrors live.py / results_sync.py:

1. **Env-gated.** With no ``TELEGRAM_BOT_TOKEN`` configured, every send and poll
   is a silent no-op, so the feature ships dark until the bot exists.
2. **No webhook, no cron.** Inbound updates are *pulled* with getUpdates behind
   an atomic claim on the singleton ``TelegramState`` row (so the connect page
   can poll for "am I linked yet?" without hammering the API). Outbound work is
   driven by an external scheduler hitting the secret-gated tick endpoint, which
   also refreshes live scores and finalizes results — so reminders *and*
   auto-finalization work even when nobody is on the site.
3. **Idempotent.** Every reminder is guarded by a ``NotificationLog`` row
   (unique per user+kind+key); a failed send rolls its row back so it retries.

Only urllib is used (no new dependency); the default urllib User-Agent is
blocked by some edges, so a real one is sent (same gotcha as the other syncs).
"""
import json
import logging
import secrets
import urllib.error
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import consts

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Configuration helpers (env-gated)
# --------------------------------------------------------------------------- #
def _token() -> str:
    return (getattr(settings, "TELEGRAM_BOT_TOKEN", "") or "").strip()


def _bot_username() -> str:
    # Accept it with or without a leading "@" (deep links need the bare handle).
    return (getattr(settings, "TELEGRAM_BOT_USERNAME", "") or "").strip().lstrip("@")


def is_configured() -> bool:
    """True when both the bot token and its @username are set (deep links need
    the username; sends only need the token)."""
    return bool(_token() and _bot_username())


def _esc(text: str) -> str:
    """Escape the three characters that matter under parse_mode=HTML."""
    return (str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# --------------------------------------------------------------------------- #
# Telegram Bot API (urllib)
# --------------------------------------------------------------------------- #
def _api_call(method: str, payload: dict):
    """POST a Bot API method as JSON. Returns the parsed response on success
    (``ok: true``), or None on any transport/HTTP/JSON error or an API ``ok:
    false`` — every failure degrades to None rather than raising."""
    token = _token()
    if not token:
        return None
    url = f"{consts.TELEGRAM_API_BASE.format(token=token)}/{method}"
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": consts.TELEGRAM_USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=consts.TELEGRAM_FETCH_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        # HTTPError (a URLError subclass) covers a 403 to an un-started chat, etc.
        logger.warning("telegram %s failed: %s", method, exc)
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("telegram %s: non-JSON response", method)
        return None
    if not parsed.get("ok"):
        logger.warning("telegram %s not ok: %s", method, parsed.get("description"))
        return None
    return parsed


def send_message(chat_id, text: str) -> bool:
    """Send one HTML message to a chat. No-op (False) without a chat id/token."""
    if not chat_id:
        return False
    resp = _api_call(consts.TELEGRAM_METHOD_SEND_MESSAGE, {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": consts.TELEGRAM_PARSE_MODE,
        "disable_web_page_preview": True,
    })
    return resp is not None


def _get_updates(offset: int):
    """Pull pending updates (messages only) from the given offset. Short poll
    (timeout 0) so it never blocks the request it runs inside."""
    return _api_call(consts.TELEGRAM_METHOD_GET_UPDATES, {
        "offset": offset,
        "timeout": 0,
        "limit": consts.TELEGRAM_GET_UPDATES_LIMIT,
        "allowed_updates": ["message"],
    })


# --------------------------------------------------------------------------- #
# Account linking (one-tap deep link)
# --------------------------------------------------------------------------- #
def link_token_for(user) -> str:
    """Return the user's current link token, issuing a fresh one only when none
    exists yet or the old one has expired. Stable across connect-page polls so
    the link the user already opened keeps working."""
    now = timezone.now()
    cutoff = now - timedelta(seconds=consts.TELEGRAM_LINK_TOKEN_MAX_AGE_SECONDS)
    if (user.telegram_link_token and user.telegram_link_token_at
            and user.telegram_link_token_at >= cutoff):
        return user.telegram_link_token
    token = secrets.token_urlsafe(consts.TELEGRAM_LINK_TOKEN_BYTES)
    user.telegram_link_token = token
    user.telegram_link_token_at = now
    user.save(update_fields=["telegram_link_token", "telegram_link_token_at"])
    return token


def deep_link(user):
    """The ``t.me/<bot>?start=<token>`` link, or None when no bot is configured."""
    username = _bot_username()
    if not username:
        return None
    return consts.TELEGRAM_DEEP_LINK.format(username=username, token=link_token_for(user))


def link_account(token: str, chat_id):
    """Resolve a (non-expired) link token to its user and attach this chat id.

    Releases the chat id from any other account first (so a re-link moves it
    cleanly under the unique constraint), enables notifications, and burns the
    token. Returns the linked user, or None for a missing/expired token."""
    if not token:
        return None
    User = get_user_model()
    cutoff = timezone.now() - timedelta(seconds=consts.TELEGRAM_LINK_TOKEN_MAX_AGE_SECONDS)
    user = User.objects.filter(
        telegram_link_token=token, telegram_link_token_at__gte=cutoff
    ).first()
    if user is None:
        return None
    with transaction.atomic():
        User.objects.filter(telegram_chat_id=chat_id).exclude(pk=user.pk).update(
            telegram_chat_id=None
        )
        user.telegram_chat_id = chat_id
        user.telegram_notify = True
        user.telegram_link_token = ""
        user.telegram_link_token_at = None
        user.save(update_fields=[
            "telegram_chat_id", "telegram_notify",
            "telegram_link_token", "telegram_link_token_at",
        ])
    return user


def process_update(update: dict):
    """Handle a single getUpdates entry: ``/start <token>`` links the account,
    ``/stop`` silences reminders. Anything else (non-private chat, non-command)
    is ignored."""
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    if chat.get("type") != consts.TELEGRAM_CHAT_TYPE_PRIVATE:
        return
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    if not chat_id or not text:
        return

    if text.startswith(consts.TELEGRAM_START_COMMAND):
        parts = text.split(maxsplit=1)
        payload = parts[1].strip() if len(parts) > 1 else ""
        if not payload:
            send_message(chat_id, consts.TG_REPLY_START_NO_TOKEN)
            return
        user = link_account(payload, chat_id)
        if user is not None:
            send_message(chat_id, consts.TG_REPLY_LINKED.format(name=_esc(user.public_name)))
        else:
            send_message(chat_id, consts.TG_REPLY_LINK_INVALID)
    elif text.startswith(consts.TELEGRAM_STOP_COMMAND):
        User = get_user_model()
        user = User.objects.filter(telegram_chat_id=chat_id).first()
        if user is not None:
            user.telegram_notify = False
            user.save(update_fields=["telegram_notify"])
            send_message(chat_id, consts.TG_REPLY_STOPPED)
        else:
            send_message(chat_id, consts.TG_REPLY_STOP_NOT_LINKED)


def poll_updates(now=None) -> int:
    """Drain pending bot updates, behind an atomic claim so concurrent callers
    (the tick, plus connect pages polling for their link) hit getUpdates at most
    once per ``consts.TELEGRAM_POLL_SECONDS``. Returns how many were processed."""
    if not _token():
        return 0
    from .models import TelegramState

    now = now or timezone.now()
    TelegramState.objects.get_or_create(pk=1)
    cutoff = now - timedelta(seconds=consts.TELEGRAM_POLL_SECONDS)
    claimed = TelegramState.objects.filter(pk=1).filter(
        Q(polled_at__isnull=True) | Q(polled_at__lt=cutoff)
    ).update(polled_at=now)
    if not claimed:
        return 0

    state = TelegramState.objects.get(pk=1)
    payload = _get_updates(state.update_offset)
    if not payload:
        return 0
    updates = payload.get("result") or []
    if not updates:
        return 0

    max_id = state.update_offset - 1
    for update in updates:
        uid = update.get("update_id")
        if uid is not None and uid > max_id:
            max_id = uid
        try:
            process_update(update)
        except Exception:  # one bad update must not stop the drain
            logger.exception("telegram: failed to process update %s", update.get("update_id"))
    TelegramState.objects.filter(pk=1).update(update_offset=max_id + 1)
    return len(updates)


# --------------------------------------------------------------------------- #
# Reminders — who still owes a prediction
# --------------------------------------------------------------------------- #
def _needing(candidate_matches, now):
    """For each linked, opted-in user, the subset of candidate_matches they can
    still predict in at least one of their leagues but haven't. Returns a list
    of (user, [matches]); users who owe nothing are omitted."""
    from .models import Membership, Prediction

    candidate_matches = list(candidate_matches)
    if not candidate_matches:
        return []

    User = get_user_model()
    recipients = list(User.objects.filter(
        telegram_chat_id__isnull=False, telegram_notify=True, is_active=True,
    ))
    if not recipients:
        return []

    memberships = list(
        Membership.objects.filter(user_id__in=[u.id for u in recipients])
        .select_related("league", "league__competition")
    )
    by_user = {}
    for m in memberships:
        by_user.setdefault(m.user_id, []).append(m)

    predicted = set(
        Prediction.objects.filter(
            membership_id__in=[m.id for m in memberships],
            match_id__in=[m.id for m in candidate_matches],
        ).values_list("membership_id", "match_id")
    )

    out = []
    for user in recipients:
        mems = by_user.get(user.id, [])
        if not mems:
            continue
        needed = []
        for match in candidate_matches:
            relevant = [m for m in mems if m.league.competition_id == match.competition_id]
            if any(
                match.is_open_for(m.league.lock_minutes, now)
                and (m.id, match.id) not in predicted
                for m in relevant
            ):
                needed.append(match)
        if needed:
            out.append((user, needed))
    return out


def _predictable_matches(now):
    """Base queryset for reminders: scheduled, both teams known, active comp."""
    from .models import Match

    return (
        Match.objects.filter(
            competition__is_active=True,
            home_team__isnull=False,
            away_team__isnull=False,
        )
        .exclude(status=consts.MatchStatus.FINISHED)
        .select_related("home_team", "away_team", "competition")
        .order_by("kickoff")
    )


def due_digests(now):
    """(user, matches) for the once-a-day morning digest: today's still-open
    matches the user hasn't predicted. Empty before the configured local hour."""
    local_now = timezone.localtime(now)
    if local_now.hour < consts.TELEGRAM_DIGEST_HOUR:
        return []
    end_of_day = local_now.replace(hour=23, minute=59, second=59, microsecond=0)
    matches = _predictable_matches(now).filter(kickoff__gt=now, kickoff__lte=end_of_day)
    return _needing(matches, now)


def due_nudges(now):
    """(user, matches) for the final pre-kickoff nudge: matches starting within
    the lead window that the user still hasn't predicted."""
    window_end = now + timedelta(minutes=consts.TELEGRAM_NUDGE_LEAD_MINUTES)
    matches = _predictable_matches(now).filter(kickoff__gt=now, kickoff__lte=window_end)
    return _needing(matches, now)


# --------------------------------------------------------------------------- #
# Message rendering
# --------------------------------------------------------------------------- #
def _match_line(match) -> str:
    local = timezone.localtime(match.kickoff)
    return consts.TG_MATCH_LINE.format(
        home=_esc(match.home_team.name_fa),
        hflag=match.home_team.flag_emoji or "",
        away=_esc(match.away_team.name_fa),
        aflag=match.away_team.flag_emoji or "",
        time=consts.to_fa_digits(local.strftime("%H:%M")),
    )


def _reminder_body(title: str, matches) -> str:
    url = f"{settings.FRONTEND_URL}{consts.TELEGRAM_REMINDER_PATH}"
    lines = [title]
    lines += [_match_line(m) for m in matches]
    lines += ["", consts.TG_REMINDER_FOOTER.format(url=url)]
    return "\n".join(lines)


def _digest_message(matches) -> str:
    return _reminder_body(consts.TG_DIGEST_TITLE, matches)


def _nudge_message(matches) -> str:
    title = consts.TG_NUDGE_TITLE.format(
        minutes=consts.to_fa_digits(consts.TELEGRAM_NUDGE_LEAD_MINUTES)
    )
    return _reminder_body(title, matches)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _send_once(user, kind: str, dedup_key: str, text: str) -> bool:
    """Send `text` to `user` unless an identical reminder already went out.
    Reserves the NotificationLog row first; deletes it again if the send fails
    so the next tick retries."""
    from .models import NotificationLog

    obj, created = NotificationLog.objects.get_or_create(
        user=user, kind=kind, dedup_key=dedup_key,
    )
    if not created:
        return False
    if send_message(user.telegram_chat_id, text):
        return True
    obj.delete()
    return False


def run_notifications(now=None) -> dict:
    """Send all due digests and nudges. Returns {'digests': n, 'nudges': n}."""
    from .models import NotificationLog

    now = now or timezone.now()
    sent = {"digests": 0, "nudges": 0}

    digest_key = timezone.localtime(now).date().isoformat()
    for user, matches in due_digests(now):
        if _send_once(user, consts.NotifyKind.DIGEST, digest_key, _digest_message(matches)):
            sent["digests"] += 1

    for user, matches in due_nudges(now):
        # Dedup per match: reserve each unseen one, then send a single message
        # listing them; roll the reservations back together if the send fails.
        reserved = []
        for match in matches:
            obj, created = NotificationLog.objects.get_or_create(
                user=user, kind=consts.NotifyKind.NUDGE, dedup_key=str(match.id),
            )
            if created:
                reserved.append((match, obj))
        if not reserved:
            continue
        if send_message(user.telegram_chat_id, _nudge_message([m for m, _ in reserved])):
            sent["nudges"] += 1
        else:
            NotificationLog.objects.filter(id__in=[o.id for _, o in reserved]).delete()

    return sent


def run_tick(now=None) -> dict:
    """The periodic job (management command + tick endpoint).

    Pulls inbound bot updates, refreshes live scores + finalizes due results for
    each active competition (so those work without app traffic), then sends due
    reminders. Cheap no-ops throughout when nothing is configured/pending."""
    from . import live, results_sync
    from .models import Competition

    now = now or timezone.now()
    result = {"polled": 0, "live": 0, "finalized": 0, "digests": 0, "nudges": 0}

    result["polled"] = poll_updates(now)
    for competition in Competition.objects.filter(is_active=True):
        if live.refresh_if_stale(competition, now):
            result["live"] += 1
        if results_sync.finalize_if_due(competition, now):
            result["finalized"] += 1
    result.update(run_notifications(now))
    return result
