# Telegram reminders & match events

The bot DMs members two distinct (independently opt-in) streams:

1. **Prediction reminders** — a once-a-day **morning digest** of the day's
   still-open matches, plus a final **nudge** shortly before kickoff, to members
   who haven't predicted yet (`telegram_notify`, on by default).
2. **Live match events** — **kickoff**, **goals**, **half-time** and
   **full-time** for matches as they happen, personalized with the member's own
   prediction and the points they earned (`telegram_notify_matches`, **off by
   default** — far higher volume, so it's strictly opt-in).

Both are built to the same philosophy as the live/results pipelines: **env-gated**
(no token ⇒ silent no-op), **no cron/worker** of our own, **atomic-claim**
de-duplication, and `urllib` only (no new dependency).

It ships **dark**: with no `TELEGRAM_BOT_TOKEN` set, every send and poll is a
no-op, and the connect UI hides itself. Nothing happens until you create a bot
and set the env vars below.

## How it works

```
Linking (one tap):
  Profile page → "اتصال به تلگرام" → opens t.me/<bot>?start=<token>
  → user taps Start → bot receives /start <token>
  → we resolve the token to the user and store their chat id → "✅ متصل شد"

Sending (no webhook, no cron):
  GitHub Actions cron (every ~10 min) → POST /api/tasks/tick/  (X-Task-Key)
  → telegram.run_tick():
       1. poll_updates()        — drain bot updates (links /start, handles /stop)
       2. live.refresh_if_stale + results_sync.finalize_if_due (bonus: works w/o traffic)
       3. run_match_events()    — DM kickoff/goal/HT/FT off the fresh live state
       4. run_notifications()   — send due morning digests + pre-kickoff nudges
```

> **Match-event timing.** Goal alerts are only as fine-grained as the tick. At
> the default ~10-min cron, several goals between two ticks collapse into the
> latest scoreline (we DM the new scoreline once, not each intermediate goal).
> **Kickoff** and **full-time** are robust regardless — kickoff also fires from
> the schedule and full-time from the official result. If you want near-live goal
> alerts, run the tick workflow more often (it's a cheap no-op when nothing is
> in play).

- **Inbound is pulled, not pushed** (getUpdates behind an atomic claim on the
  singleton `TelegramState` row) — no public webhook to expose. The profile
  page also polls `GET /api/me/telegram/`, which drains updates, so the link
  completes within a couple of seconds of tapping Start.
- **Idempotent.** Every DM is guarded by a `NotificationLog` row
  (`unique(user, kind, dedup_key)`): the digest is keyed by the local date, the
  nudge / kickoff / half-time / full-time by the match id, and a **goal** by the
  scoreline (`"<match id>:<home>-<away>"`, so each new scoreline fires once). A
  failed send rolls its row back so it retries.
- **Per-league locks are respected** (reminders): a user is only reminded about a
  match they can still predict (`Match.is_open_for(league.lock_minutes)`) and
  haven't.
- **Match events are personalized.** `run_match_events` reads each in-window
  match's `live_*` fields (refreshed earlier in the same tick) plus its official
  result, then DMs every `telegram_notify_matches` member — with their own
  prediction, an "on track" hint when the live score already matches it, and the
  points they earned at full time (summed across their leagues, since a member
  can predict the same match differently in each). Full-time prefers the official
  result and falls back to the live final when the official sync hasn't landed.

## One-time setup (the part only you can do)

1. **Create the bot** in Telegram with **@BotFather** → `/newbot` → pick a name
   and a username (e.g. `worldcup_predict_bot`). BotFather returns a **token**
   like `123456:ABC-...`.
2. **(Recommended) disable group privacy is *not* needed** — we only use private
   chats. You can leave defaults. Optionally set `/setdescription` and
   `/setcommands` (`start`, `stop`).
3. **Set the backend env vars** (Render dashboard → worldcup-api → Environment):
   | Var | Value |
   |-----|-------|
   | `TELEGRAM_BOT_TOKEN` | the BotFather token |
   | `TELEGRAM_BOT_USERNAME` | the bot's @username (with or without `@`) |
   | `TASK_TRIGGER_KEY` | any long random string (e.g. `openssl rand -hex 24`) |
4. **Add the GitHub Actions secrets** (repo → Settings → Secrets and variables →
   Actions):
   | Secret | Value |
   |--------|-------|
   | `TICK_URL` | `https://<backend-host>/api/tasks/tick/` |
   | `TASK_TRIGGER_KEY` | the **same** value as the backend env var |
   The workflow at `.github/workflows/telegram-tick.yml` POSTs the tick endpoint
   every ~10 minutes. (You can also run it on demand from the Actions tab.)

That's it. Members then go to **پروفایل من → اتصال به تلگرام**, tap once, and
start getting reminders.

## Config knobs (all in `predictions/consts.py`)

| Constant | Default | Meaning |
|----------|---------|---------|
| `TELEGRAM_NUDGE_LEAD_MINUTES` | 30 | nudge this long before kickoff |
| `TELEGRAM_DIGEST_HOUR` | 9 | morning digest goes out at/after this local hour |
| `TELEGRAM_LINK_TOKEN_MAX_AGE_SECONDS` | 3600 | how long a connect link stays valid |
| `TELEGRAM_POLL_SECONDS` | 2 | min spacing between getUpdates drains |
| `TELEGRAM_EVENT_WINDOW_HOURS` | 4 | only DM match events for matches whose kickoff is within this window (keeps a fresh opt-in from being flooded with older matches) |
| `TELEGRAM_KICKOFF_GRACE_MINUTES` | 20 | a "kickoff" DM only fires this soon after the real kickoff (so a late opt-in / late feed doesn't get a stale "kickoff!") |

The digest "today" and the times shown use `settings.TIME_ZONE` (Tehran).

## Testing / running locally

```bash
# Unit + endpoint tests (network fully mocked, token unset):
.venv/bin/python manage.py test predictions.tests.test_telegram --settings=config.settings_test

# Run one tick by hand (no-op without a token configured):
.venv/bin/python manage.py send_telegram_notifications
```

## Endpoints

| Method | Path | Notes |
|--------|------|-------|
| `GET/PATCH` | `/api/me/telegram/` | link status + connect deep link; PATCH `{notify}` (reminders) / `{notify_matches}` (match events) / `{unlink}`. GET also drains bot updates. |
| `POST` | `/api/tasks/tick/` | scheduler-only; gated by `X-Task-Key` == `TASK_TRIGGER_KEY` (403 when the key is unset). |

## Not in v1 (clean follow-ups)

- **Group "who-called-it" recaps** posted to a league's Telegram group when a
  match finalizes — `predictions/recap.py` already computes the superlatives;
  this would add a `League.telegram_chat_id` + a `/register` group command and
  reuse `run_tick`.
