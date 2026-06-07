# Architecture

## Overview

Two services in one repository:

| Service | Tech | Port | Responsibility |
|---------|------|------|----------------|
| **API + Admin** | Django 5.2, DRF | 8001 | Database, scoring engine, JSON API, admin panel |
| **Frontend** | Next.js 16, React 19 | 3077 | All user-facing UI (Persian, RTL) |
| **Database** | PostgreSQL (Supabase) | 54322 | Persistent storage |
| **Auth** | Clerk (hosted) | — | Sign-in/up, sessions, social login |

```
┌──────────────┐   Clerk JWT (Bearer)   ┌──────────────┐   psycopg   ┌────────────┐
│  Next.js     │ ─────────────────────> │  Django API  │ ──────────> │  Postgres  │
│  (browser +  │                        │  (DRF)       │             │ (Supabase) │
│   SSR :3077) │ <───────── JSON ────── │   :8001      │             │   :54322   │
└──────┬───────┘                        └──────┬───────┘             └────────────┘
       │ Clerk widgets                         │
       v                                       v
   Clerk Frontend API                     Django Admin (/admin)
   (sign in / up)                         enter results, tune scoring
```

## Why this split

- The user wanted a **Django backend** (admin panel + Python scoring) **and** a
  **Next.js frontend**. Django keeps the ready-made admin and the scoring engine;
  Next.js gives a modern UI with first-class Clerk integration (`@clerk/nextjs`).
- The boundary is a small JSON API. The frontend never touches the database.

## Authentication flow (detailed)

1. **Sign in** — Next.js renders Clerk's `<SignIn/>`/`<SignUp/>`. Clerk manages the
   session in the browser and issues short-lived session **JWTs**.
2. **Authorized API calls** — Next.js attaches the JWT to every Django request:
   - Server Components → `serverFetch()` → `auth().getToken()` (`src/lib/server.ts`)
   - Client Components → `apiFetch()` with `useAuth().getToken()` (`src/lib/api.ts`)
3. **Verification (Django)** — `accounts/authentication.py::ClerkAuthentication`:
   - extracts the `Bearer` token,
   - `accounts/clerk.py::verify_session_token` validates the signature against
     Clerk's **JWKS** (`CLERK_JWKS_URL`) and the issuer (`CLERK_FRONTEND_API_URL`),
   - `accounts/clerk.py::get_or_create_user` maps the token `sub` to a local
     `accounts.User`, pulling email/name from claims or the Clerk Backend API.
4. **Authorization** — DRF runs the view with `request.user`; views check league
   membership (`_get_membership`).

The local `User` is a thin mirror keyed by `clerk_id`. Passwords are unused for
end users (`set_unusable_password`); Clerk owns credentials. The admin panel uses
a normal Django superuser.

## Request lifecycle (example: open a league)

```
GET /l/<slug>            (Next.js Server Component)
  └─ layout.tsx: serverFetch(`/leagues/<slug>/`)  ── Bearer JWT ──▶ Django
        Django: ClerkAuth → membership check → JSON {name, scoring, ...}
  └─ page.tsx: serverFetch leaderboard + matches (parallel)
  └─ render Persian/RTL HTML
```

## Scoring recompute

Scores are **stored** (`MatchScore`) and recomputed by a Django `post_save` signal
whenever a `Match` result changes (`predictions/signals.py`). This means entering a
score in the admin instantly updates every member's points across every league on
that competition. See [SCORING.md](SCORING.md).

## Configuration

All config is environment-driven (`.env` for Django, `.env.local` for Next.js).
Key variables: `DATABASE_URL`, `CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`,
`CLERK_FRONTEND_API_URL`, `CORS_ALLOWED_ORIGINS`, `NEXT_PUBLIC_API_URL`. See
`.env.example` and `frontend/.env.local.example`.
