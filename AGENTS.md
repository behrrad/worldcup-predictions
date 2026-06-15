# AGENTS.md — Onboarding & contribution guide

Read this before changing code. It exists so any agent (or human) can become
productive fast and **modify the project without introducing bugs**. It captures
the architecture, the conventions, and the non-obvious gotchas that already cost
us debugging time.

The golden rule: **run the tests before and after every change.**

```bash
.venv/bin/python manage.py test --settings=config.settings_test   # backend
cd frontend && pnpm exec tsc --noEmit                             # frontend types
```

---

## 1. What this is

A Persian (RTL) World Cup prediction league. Friends create/join **leagues**,
predict match scores before kickoff, and earn points after each match. One
person account can belong to many leagues; each league has its own scoring config.

Two deployables, one repo:

- **Django** (`config/`, `accounts/`, `predictions/`) — JSON API + admin panel +
  the scoring engine + the database. Runs on **:8001**.
- **Next.js** (`frontend/`) — the entire user-facing UI. Runs on **:3077**.

Auth is **Clerk**. The browser holds the Clerk session; the API trusts a verified
Clerk JWT.

---

## 2. Request & auth flow (read this once, fully)

```
1. User signs in via Clerk widgets in Next.js (<SignIn/> / <SignUp/>).
2. Next.js calls the Django API with the Clerk session JWT:
        Authorization: Bearer <jwt>
   - Server Components: token = await (await auth()).getToken()   (src/lib/server.ts)
   - Client Components: token = await useAuth().getToken()        (src/lib/api.ts)
3. Django's ClerkAuthentication (accounts/authentication.py):
        - verifies the JWT signature against Clerk's JWKS (public keys)
        - checks issuer == CLERK_FRONTEND_API_URL
        - maps `sub` (Clerk user id) -> local accounts.User (get_or_create)
        - email/name come from the token claims, else from Clerk's Backend API
4. DRF view runs with request.user set. Returns JSON.
```

There is **no Django session login** for end users and **no `<SignedIn>`/template
auth** — that earlier approach was removed. Django's own login is only for the
**admin panel** (superusers).

The **one exception** to "every endpoint needs a Clerk JWT" is the results export:
`GET /api/export/<export_key>.xlsx` is public (`AllowAny`, no auth class) and gated
solely by the league's unguessable `export_key`. The owner shares the key/link so
anyone can download the standings spreadsheet. It's IP-rate-limited (`ExportThrottle`)
and the builder hides predictions for matches that haven't locked yet.

---

## 3. File map (where things live)

### Backend
| Path | Responsibility |
|------|----------------|
| `config/settings.py` | All settings; reads `.env`. Clerk + CORS + DRF config near the bottom. |
| `config/settings_test.py` | Test settings: in-memory SQLite, dummy Clerk, fast hashing. |
| `config/urls.py` | Only `admin/` and `api/` (the HTML frontend was removed). |
| `accounts/models.py` | Custom `User` (email is the login, has `clerk_id`). |
| `accounts/clerk.py` | **JWT verification + user sync.** The Clerk integration core. |
| `accounts/authentication.py` | DRF auth class that calls `clerk.py`. |
| `accounts/admin.py` | Admin for users. |
| `predictions/models.py` | `Competition, Team, Match, League, Membership, Prediction, MatchScore`. |
| `predictions/scoring.py` | **The scoring engine** + recompute + leaderboard (official + the live provisional view). |
| `predictions/live.py` | Live in-play scores (ESPN primary, Varzesh3 fallback; lazy fetch-on-read). Writes `Match.live_*` via `queryset.update()` only — **never `save()`**, which would finalize the result and trigger scoring. |
| `predictions/results_sync.py` | Official results from football-data.org: core of the `sync_results` command **and** `finalize_if_due` — the lazy, claim-gated auto-finalization the live endpoint triggers once a match looks over (no cron). The only pipeline allowed to `Match.save()` provider data. |
| `predictions/telegram.py` | **Telegram reminders** (one-tap linking + morning digest + pre-kickoff nudge) **and live match-event DMs** (kickoff/goal/half-time/full-time, personalized with the member's pick + points; separate `telegram_notify_matches` opt-in). Same env-gated, no-cron, atomic-claim philosophy as live/results. `run_tick` is driven by the secret-gated `/api/tasks/tick/` endpoint (GitHub Actions cron) and also refreshes live + finalizes results. See `docs/TELEGRAM.md`. |
| `predictions/export.py` | Builds a league's results **.xlsx** (member-per-3-columns layout). Blanks out predictions for matches that haven't locked yet. |
| `predictions/signals.py` | On `Match` save → recompute everyone's scores. |
| `predictions/api_views.py` | All JSON endpoints (function-based DRF views). |
| `predictions/api_urls.py` | API routes (note: `<str:slug>`, not `<slug:slug>`). |
| `predictions/admin.py` | Admin: enter results inline, tune scoring, recompute actions. |
| `predictions/consts.py` | **Every constant & UI string** (see convention §4). |
| `predictions/data/worldcup2026.json` | **The real, official 2026 schedule** — 48 teams (groups A–L) + all 104 matches with exact UTC kickoffs. Source of truth for the seed. |
| `predictions/seed_data.py` | Competition name/slug + the small "test cup" data (compressed timeline). |
| `predictions/management/commands/` | `seed_worldcup2026` (loads the real schedule from the JSON), `seed_test_tournament`, `compute_scores`, `sync_results`, `send_telegram_notifications` (one reminder tick). |
| `*/tests/` | Test packages (run with `settings_test`). |

### Frontend (`frontend/src/`)
| Path | Responsibility |
|------|----------------|
| `proxy.ts` | Clerk middleware. **Next 16 calls it `proxy.ts`, in `src/`.** |
| `app/layout.tsx` | `<ClerkProvider>` (Persian `faIR`), RTL `<html dir="rtl">`, Vazirmatn font. |
| `app/page.tsx` | Public landing (redirects signed-in users to `/dashboard`). |
| `app/sign-in/[[...sign-in]]/`, `app/sign-up/[[...sign-up]]/` | Clerk widgets. |
| `app/dashboard/` | My leagues, create/join. |
| `app/l/[slug]/` | League area: `layout.tsx` (tabs) + overview/predictions/leaderboard/matches/rules/match. |
| `components/` | `Header`, `LeagueTabs`, `JoinLeague`, `CreateLeagueForm`, `PredictionsForm`. |
| `lib/api.ts` | `apiFetch(path, token, opts)` — isomorphic fetch to Django. |
| `lib/server.ts` | `serverFetch(path)` — adds the Clerk token in Server Components. |
| `lib/format.ts` | `fmtDateTime` (Jalali), `fa()` (Persian digits). |
| `lib/types.ts` | TypeScript types mirroring the API JSON. |

---

## 4. Conventions (follow these)

1. **No literal strings/values in Python logic.** All constants, choices, labels,
   Persian UI text, scoring defaults, etc. live in `predictions/consts.py` (and
   `accounts/consts.py`). Reference them; don't hardcode. This was an explicit
   project requirement. Template/JSX text in the Next.js frontend is fine inline.
2. **Persian + RTL everywhere** in the UI. New pages use the same CSS classes in
   `frontend/src/app/globals.css`. Dates via `fmtDateTime` (Jalali), numbers via `fa()`.
3. **Scoring is data-driven.** Never hardcode point values; read them from the
   `League` instance (they're admin-editable per league).
4. **API responses are plain dicts** built in `api_views.py` (floats for points,
   ISO strings for datetimes). Keep `lib/types.ts` in sync when you change shapes.
5. **Every new endpoint/logic gets a test.** See §7.

---

## 5. Gotchas (already cost us time — don't relearn them)

- **Next.js 16 renamed middleware → `proxy.ts`**, and with `--src-dir` it must be
  at `src/proxy.ts`. Clerk's middleware is the default export there.
- **Clerk v7 removed `<SignedIn>`/`<SignedOut>`.** Use `useUser()`/`useAuth()` or
  server `auth()`. `afterSignOutUrl` lives on `<ClerkProvider>`, not `<UserButton>`.
- **Next 16 route `params` is a Promise** — `const { slug } = await params`.
- **Django `<slug:…>` is ASCII-only.** League slugs are Persian (`allow_unicode`),
  so API routes use **`<str:slug>`**. Don't switch them back.
- **Clerk Backend API blocks the default `Python-urllib` User-Agent with 403.**
  `accounts/clerk.py` sends an explicit `User-Agent`. Keep it.
- **Turbopack dev crashed** under load (`Map maximum size exceeded`). The dev
  script uses `--webpack` on purpose (`frontend/package.json`).
- **Ports:** Django **8001**, Next **3077**, Supabase Postgres **54322**. CORS in
  `settings.py` must allow the Next origin.

---

## 6. How to extend (recipes)

### Add an API endpoint
1. Add a function view in `predictions/api_views.py` (use `@api_view`, build a dict).
2. Route it in `predictions/api_urls.py` (use `<str:slug>` for league slugs).
3. Add a type in `frontend/src/lib/types.ts` and call it via `serverFetch`/`apiFetch`.
4. Add a test in `predictions/tests/test_api.py`.

### Add a frontend page
1. Create `frontend/src/app/.../page.tsx` (Server Component for reads; remember
   `params` is a Promise).
2. Fetch with `serverFetch("/...")`; for mutations make a `"use client"` component
   that uses `useAuth().getToken()` + `apiFetch`.
3. Reuse classes from `globals.css`; format with `fmtDateTime` / `fa`.

### Change scoring rules
- Defaults: `predictions/consts.py` (`DEFAULT_POINTS_*`, multipliers, lock minutes).
- Per-league overrides: editable in the **admin** (`/admin/` → مسابقه‌های پیش‌بینی).
- Logic: `predictions/scoring.py` (`base_tier`, `score_prediction`). **Update
  `predictions/tests/test_scoring.py` to match.**

### Add another tournament (e.g. a domestic league)
- Create a `Competition` + `Team`s + `Match`es (admin, or a new seed command —
  `seed_worldcup2026.py` is a good model for a JSON-driven loader,
  `seed_test_tournament.py` for a procedural one). Leagues reference a
  Competition, so the whole flow works unchanged.

### Update the World Cup schedule
- The real data lives in `predictions/data/worldcup2026.json` (teams keyed by
  `code`; matches keyed by `match_number` with `kickoff_utc`). Edit it, then run
  `python manage.py seed_worldcup2026` — it validates the whole file first and
  **upserts by match number, preserving predictions/scores/results**. Use
  `--reset` for a destructive clean rebuild. Per-match tweaks are also editable
  in the admin (تیم‌ها / بازی‌ها).

---

## 7. Testing workflow (summary — full version in docs/TESTING.md)

- Backend tests live in `accounts/tests/` and `predictions/tests/` and run on
  fast in-memory SQLite with mocked Clerk:
  `python manage.py test --settings=config.settings_test`
- When you touch **scoring**, add cases to `test_scoring.py`.
- When you touch an **endpoint**, add cases to `test_api.py`.
- When you touch **models/lock logic**, add cases to `test_models.py`.
- Frontend: keep `pnpm exec tsc --noEmit` clean; types in `lib/types.ts` are the
  contract with the backend.

---

## 8. Useful commands

```bash
# Backend
.venv/bin/python manage.py runserver 127.0.0.1:8001
.venv/bin/python manage.py seed_worldcup2026 [--reset] [--file <path>]   # real 2026 schedule
.venv/bin/python manage.py compute_scores [--competition <slug>]
.venv/bin/python manage.py sync_results [--dry-run]   # pull finished scores from football-data.org
.venv/bin/python manage.py test --settings=config.settings_test

# Frontend
cd frontend && pnpm dev            # :3077 (webpack)
cd frontend && pnpm exec tsc --noEmit
cd frontend && pnpm build
```
