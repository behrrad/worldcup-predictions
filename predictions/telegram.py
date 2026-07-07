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
def _linked_users(notify_field: str):
    """Linked, active users opted into a given DM stream. `notify_field` selects
    the opt-in: `telegram_notify` (reminders) or `telegram_notify_matches`
    (match events) — keeping "who is reachable" defined in one place."""
    User = get_user_model()
    return User.objects.filter(
        telegram_chat_id__isnull=False, is_active=True, **{notify_field: True},
    )


def _needing(candidate_matches, now):
    """For each linked, opted-in user, the subset of candidate_matches they can
    still predict in at least one of their leagues but haven't. Returns a list
    of (user, [matches]); users who owe nothing are omitted."""
    from .models import Membership, Prediction

    candidate_matches = list(candidate_matches)
    if not candidate_matches:
        return []

    recipients = list(_linked_users("telegram_notify"))
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


def _fixtures_base():
    """Both teams known, active competition, ready to render (teams/competition
    preselected, ordered by kickoff). The shared base for the reminder and
    match-event match queries, which each add their own time/status filter."""
    from .models import Match

    return (
        Match.objects.filter(
            competition__is_active=True,
            home_team__isnull=False,
            away_team__isnull=False,
        )
        .select_related("home_team", "away_team", "competition")
        .order_by("kickoff")
    )


def _predictable_matches(now):
    """Base queryset for reminders: scheduled, both teams known, active comp."""
    return _fixtures_base().exclude(status=consts.MatchStatus.FINISHED)


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
def _sides(match):
    """(home name+flag, away name+flag), names HTML-escaped — the shared bits
    every fixture/scoreline render needs."""
    return (
        _esc(match.home_team.name_fa), match.home_team.flag_emoji or "",
        _esc(match.away_team.name_fa), match.away_team.flag_emoji or "",
    )


def _match_line(match) -> str:
    local = timezone.localtime(match.kickoff)
    home, hflag, away, aflag = _sides(match)
    return consts.TG_MATCH_LINE.format(
        home=home, hflag=hflag, away=away, aflag=aflag,
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


# --------------------------------------------------------------------------- #
# Live match events — kickoff / goals / half-time / full-time
# --------------------------------------------------------------------------- #
# A second, opt-in DM stream (User.telegram_notify_matches) that narrates a match
# as it happens, personalized with the member's own prediction. State comes from
# the live_* fields (refreshed earlier in the same tick) plus the official result;
# idempotency is the same NotificationLog (user, kind, dedup_key) guard as the
# reminders — every event fires at most once per recipient. Because the live feed
# is sampled per tick (not per second), goal alerts are best-effort: a flurry of
# goals between two ticks collapses into the latest scoreline. Kickoff and
# full-time are robust (they also fire from the schedule / official result).
def _match_event_recipients():
    """Linked, active members who opted into match-event DMs (a separate switch
    from the reminder opt-in)."""
    return list(_linked_users("telegram_notify_matches"))


def _event_window_matches(now):
    """Matches worth narrating right now: both teams known, in an active comp,
    and either already kicked off or carrying live state — bounded to a recent
    window so a fresh opt-in isn't flooded with older matches."""
    cutoff = now - timedelta(hours=consts.TELEGRAM_EVENT_WINDOW_HOURS)
    return list(
        _fixtures_base()
        .filter(kickoff__gte=cutoff)
        .filter(Q(kickoff__lte=now) | ~Q(live_status=consts.LiveStatus.NONE))
    )


def _minute_value(minute) -> int:
    """The base match-minute as an int (the number before any '+'), or -1 when
    the live clock is missing/unparseable (e.g. "45+4" -> 45, "67" -> 67)."""
    head = (minute or "").split("+", 1)[0].strip()
    return int(head) if head.isdigit() else -1


def _events_for(match, now):
    """The match-event entries this match currently warrants, each a dict with a
    `kind`, a dedup `key`, the rendering `phase`, and the score it carries. The
    NotificationLog guard downstream makes each one fire at most once."""
    live = match.live_status
    has_live_score = (
        match.live_home_score is not None and match.live_away_score is not None
    )
    over_official = match.is_finished
    # Only treat a live "full time" as over when it actually carries a scoreline:
    # a FT status with NULL scores (a partial/stale live row) would otherwise feed
    # None into the scorer at full time and crash the whole tick.
    over_live = live == consts.LiveStatus.FULL_TIME and has_live_score
    over = over_official or over_live
    since_kickoff = now - match.kickoff
    events = []

    # Kickoff: only just after the real kickoff (not for a match discovered
    # mid-play by a late opt-in/feed) and only while it isn't already over.
    if not over and timedelta() <= since_kickoff <= timedelta(
        minutes=consts.TELEGRAM_KICKOFF_GRACE_MINUTES
    ):
        events.append({
            "kind": consts.NotifyKind.KICKOFF, "key": str(match.id),
            "phase": consts.NotifyKind.KICKOFF, "hs": None, "as": None,
        })

    # Goal: a changed in-play scoreline with at least one goal on the board. Only
    # while the ball is in play (a match first seen at half-time announces the
    # score through the half-time event, not a phantom "goal").
    if live == consts.LiveStatus.LIVE and has_live_score \
            and match.live_home_score + match.live_away_score > 0:
        events.append({
            "kind": consts.NotifyKind.GOAL,
            "key": consts.NOTIFY_GOAL_KEY.format(
                match_id=match.id, home=match.live_home_score, away=match.live_away_score,
            ),
            "phase": consts.NotifyKind.GOAL,
            "hs": match.live_home_score, "as": match.live_away_score,
            "minute": match.live_minute,
        })

    if live == consts.LiveStatus.HALFTIME and has_live_score:
        events.append({
            "kind": consts.NotifyKind.HALFTIME, "key": str(match.id),
            "phase": consts.NotifyKind.HALFTIME,
            "hs": match.live_home_score, "as": match.live_away_score,
        })

    # Second-half kickoff: back in play with the clock resumed in the second half
    # (it restarts at 46'). Upper-bounded so a match first observed deep in the
    # half doesn't get a stale "second half started".
    if live == consts.LiveStatus.LIVE and (
        consts.SECOND_HALF_MINUTE <= _minute_value(match.live_minute)
        <= consts.SECOND_HALF_MINUTE_MAX
    ):
        events.append({
            "kind": consts.NotifyKind.SECOND_HALF, "key": str(match.id),
            "phase": consts.NotifyKind.SECOND_HALF,
            "hs": match.live_home_score, "as": match.live_away_score,
        })

    if over:
        # Prefer the official result (it carries the points members earned); fall
        # back to the live final when the official sync hasn't landed yet.
        if over_official:
            hs, as_ = match.home_score, match.away_score
        else:
            hs, as_ = match.live_home_score, match.live_away_score
        events.append({
            "kind": consts.NotifyKind.FULLTIME, "key": str(match.id),
            "phase": consts.NotifyKind.FULLTIME, "hs": hs, "as": as_,
        })

    return events


def _predictions_index(recipients, matches):
    """{(user_id, match_id): [Prediction, ...]} across the recipients' leagues —
    a member can predict the same match differently in several leagues."""
    from .models import Prediction

    preds = Prediction.objects.filter(
        match_id__in=[m.id for m in matches],
        membership__user_id__in=[u.id for u in recipients],
    ).select_related("membership", "membership__league")
    index = {}
    for p in preds:
        index.setdefault((p.membership.user_id, p.match_id), []).append(p)
    return index


def _fmt_points(value) -> str:
    """A summed Decimal of points as a compact Persian-digit string (no trailing
    zeros): «۵», «۷٫۵»."""
    text = format(value.normalize(), "f") if hasattr(value, "normalize") else str(value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return consts.to_fa_digits(text)


def _event_title(event) -> str:
    phase = event["phase"]
    if phase == consts.NotifyKind.KICKOFF:
        return consts.TG_EVENT_KICKOFF_TITLE
    if phase == consts.NotifyKind.HALFTIME:
        return consts.TG_EVENT_HALFTIME_TITLE
    if phase == consts.NotifyKind.SECOND_HALF:
        return consts.TG_EVENT_SECONDHALF_TITLE
    if phase == consts.NotifyKind.FULLTIME:
        return consts.TG_EVENT_FULLTIME_TITLE
    # The minute comes straight from the live provider, so escape it before it
    # lands in the parse_mode=HTML message (same care as the team names).
    minute = _esc((event.get("minute") or "").strip())
    clock = consts.TG_EVENT_GOAL_CLOCK.format(minute=consts.to_fa_digits(minute)) if minute else ""
    return consts.TG_EVENT_GOAL_TITLE.format(clock=clock)


def _event_fixture(event, match) -> str:
    home, hflag, away, aflag = _sides(match)
    if event["hs"] is None or event["as"] is None:
        return consts.TG_EVENT_FIXTURE_LINE.format(
            hflag=hflag, home=home, away=away, aflag=aflag)
    return consts.TG_EVENT_SCORE_LINE.format(
        hflag=hflag, home=home, away=away, aflag=aflag,
        hs=consts.to_fa_digits(event["hs"]), **{"as": consts.to_fa_digits(event["as"])},
    )


def _distinct_picks(predictions):
    """Sorted unique (home, away) scorelines the member predicted for the match."""
    return sorted({(p.predicted_home, p.predicted_away) for p in predictions})


def _personal_lines(event, match, predictions) -> list:
    """The personalized tail of the message: the member's pick(s), an on-track
    hint mid-match, and the points they earned at full time."""
    picks = _distinct_picks(predictions)
    is_final = event["phase"] == consts.NotifyKind.FULLTIME
    lines = []

    if not picks:
        # Only nag about a missed prediction at full time (mid-match it's noise).
        return [consts.TG_EVENT_NO_PICK] if is_final else []

    rendered = consts.TG_EVENT_PICK_JOIN.join(
        consts.TG_EVENT_PICK.format(
            home=consts.to_fa_digits(h), away=consts.to_fa_digits(a))
        for h, a in picks
    )
    lines.append(consts.TG_EVENT_YOUR_PICK.format(picks=rendered))

    if is_final:
        from . import scoring

        total = sum(
            scoring.provisional_points(
                p.membership.league, match, p, event["hs"], event["as"],
            )[0]
            for p in predictions
        )
        lines.append(
            consts.TG_EVENT_POINTS.format(points=_fmt_points(total))
            if total else consts.TG_EVENT_POINTS_NONE
        )
    elif event["hs"] is not None and (event["hs"], event["as"]) in set(picks):
        # Mid-match and the live scoreline already matches a prediction exactly.
        lines.append(consts.TG_EVENT_ON_TRACK)

    return lines


def _render_event(event, match, predictions) -> str:
    lines = [_event_title(event), _event_fixture(event, match)]
    lines += _personal_lines(event, match, predictions)
    return "\n".join(lines)


def run_match_events(now=None) -> dict:
    """Send live match-event DMs (kickoff/goal/half-time/full-time) to opted-in
    members, personalized with their prediction. Returns {'events': n}."""
    now = now or timezone.now()
    sent = {"events": 0}

    # Cheapest gate first: most ticks have no in-window match, so skip loading the
    # whole opted-in recipient set when there's nothing to narrate.
    matches = _event_window_matches(now)
    if not matches:
        return sent
    recipients = _match_event_recipients()
    if not recipients:
        return sent

    preds = _predictions_index(recipients, matches)
    for match in matches:
        for event in _events_for(match, now):
            for user in recipients:
                # Rendered per recipient: the full-time points line depends on the
                # member's own leagues/scoring, so text can't be shared across
                # members even when their predicted scoreline matches.
                text = _render_event(event, match, preds.get((user.id, match.id), []))
                if _send_once(user, event["kind"], event["key"], text):
                    sent["events"] += 1

    return sent


def run_tick(now=None) -> dict:
    """The periodic job (management command + tick endpoint).

    Pulls inbound bot updates, refreshes live scores + finalizes due results for
    each active competition (so those work without app traffic), then sends due
    match-event DMs and prediction reminders. Cheap no-ops throughout when
    nothing is configured/pending."""
    from . import bracket, live, results_sync
    from .models import Competition

    now = now or timezone.now()
    result = {
        "polled": 0, "live": 0, "finalized": 0, "advanced": 0,
        "events": 0, "digests": 0, "nudges": 0,
    }

    result["polled"] = poll_updates(now)
    for competition in Competition.objects.filter(is_active=True):
        if live.refresh_if_stale(competition, now):
            result["live"] += 1
        if results_sync.finalize_if_due(competition, now):
            result["finalized"] += 1
        # Propagate freshly-decided knockout matches into the next round's empty
        # slots so each round opens for prediction as the previous one finishes.
        result["advanced"] += bracket.advance_bracket(competition)
    # Match events first (uses the freshly-refreshed live state + official result),
    # then the prediction reminders.
    result.update(run_match_events(now))
    result.update(run_notifications(now))
    return result
