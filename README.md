# پیش‌بینی جام جهانی — World Cup Prediction League

A friends' World Cup prediction competition: predict match scores, earn points,
climb the leaderboard. Supports **multiple independent tournaments** (leagues)
for different groups of friends.

- **Backend:** Django 5.2 (LTS) REST API + Django admin panel, PostgreSQL (Supabase)
- **Frontend:** Next.js 16 (App Router) + React 19, Persian/RTL
- **Auth:** Clerk (hosted sign-in/up, social login) verified server-side
- **Language:** Persian (فارسی), right-to-left, Jalali dates

> New to this codebase (human or agent)? Read **[AGENTS.md](AGENTS.md)** first —
> it is the onboarding map. Deep dives live in **[docs/](docs/)**.

---

## Architecture at a glance

```
  Browser ──> Next.js (3077)  ──fetch w/ Clerk JWT──>  Django API (8001) ──> Postgres (Supabase, 54322)
                 │  @clerk/nextjs                          │  DRF + ClerkAuthentication
                 │  Persian RTL UI                         └──> Django Admin  (enter results, tune scoring)
                 └─ Clerk widgets (sign in/up)
```

- The browser authenticates with **Clerk**. Every API call carries the Clerk
  session JWT as `Authorization: Bearer <token>`.
- **Django** verifies that JWT against Clerk's public keys (JWKS), maps it to a
  local `User`, and serves JSON. The **scoring engine** and **admin panel** live here.
- **Next.js** is the only frontend. It calls the Django API (server components use
  the token from `auth()`, client components from `useAuth()`).

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.13 | `uv` recommended for the venv |
| Node | ≥ 20 (tested on 24) | `pnpm` |
| PostgreSQL | Supabase local or any Postgres | default port `54322` (Supabase) |
| Clerk account | — | a development instance + keys |

---

## Setup

### 1. Backend (Django API)

```bash
# from the repo root
uv venv --python 3.13 .venv
uv pip install --python .venv -r requirements.txt

cp .env.example .env        # then fill in DATABASE_URL + CLERK_* values
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_worldcup2026     # loads the 2026 teams + fixtures
.venv/bin/python manage.py createsuperuser       # for the /admin panel
.venv/bin/python manage.py runserver 127.0.0.1:8001
```

`.env` keys (see `.env.example`):

```
DATABASE_URL=postgres://postgres:postgres@127.0.0.1:54322/postgres   # local Supabase
CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
CLERK_FRONTEND_API_URL=https://<your-instance>.clerk.accounts.dev
CORS_ALLOWED_ORIGINS=http://localhost:3077,http://127.0.0.1:3077
```

### 2. Frontend (Next.js)

```bash
cd frontend
pnpm install
cp .env.local.example .env.local     # fill in the same Clerk keys + API URL
pnpm dev                              # http://localhost:3077
```

`frontend/.env.local` keys:

```
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
NEXT_PUBLIC_API_URL=http://127.0.0.1:8001
```

Open **http://localhost:3077**.

---

## Running the tests

```bash
# Backend (fast, in-memory SQLite, no network) — 60+ tests
.venv/bin/python manage.py test --settings=config.settings_test

# Frontend type-check
cd frontend && pnpm exec tsc --noEmit
```

See **[docs/TESTING.md](docs/TESTING.md)** for the full testing workflow and how
to add tests when you build new features.

---

## Repository layout

```
.
├── config/            # Django project (settings, urls, settings_test)
├── accounts/          # Custom User (email login) + Clerk auth bridge
├── predictions/       # Domain: models, scoring, API, admin, seed data, tests
├── frontend/          # Next.js app (App Router, @clerk/nextjs, RTL)
├── docs/              # Architecture / scoring / API / frontend / testing docs
├── AGENTS.md          # Onboarding guide for agents & new contributors
├── requirements.txt
└── manage.py
```

---

## Ports

| Service | URL |
|---------|-----|
| Next.js frontend | http://localhost:3077 |
| Django API + admin | http://127.0.0.1:8001 (`/api/`, `/admin/`) |
| Postgres (Supabase) | 127.0.0.1:54322 |
