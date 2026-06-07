# Frontend (Next.js)

App Router, React 19, TypeScript, Persian/RTL. Lives in `frontend/`.

> **Next.js 16 differs from older versions.** Read `frontend/AGENTS.md` and, when
> unsure, the bundled docs in `frontend/node_modules/next/dist/docs/`.

## Routing map

| Route | File | Notes |
|-------|------|-------|
| `/` | `app/page.tsx` | Public landing; redirects signed-in users to `/dashboard`. |
| `/sign-in`, `/sign-up` | `app/sign-in/[[...sign-in]]/`, `app/sign-up/[[...sign-up]]/` | Clerk catch-all widgets. |
| `/dashboard` | `app/dashboard/page.tsx` | My leagues + join/create. |
| `/leagues/new` | `app/leagues/new/page.tsx` | Create-league form. |
| `/l/[slug]` | `app/l/[slug]/layout.tsx` + `page.tsx` | League layout (title + tabs) wraps all sub-pages. |
| `/l/[slug]/predictions` | `predictions/page.tsx` | Editable score inputs (client form). |
| `/l/[slug]/leaderboard` | `leaderboard/page.tsx` | Standings. |
| `/l/[slug]/matches` | `matches/page.tsx` | My predictions + points history. |
| `/l/[slug]/match/[matchId]` | `match/[matchId]/page.tsx` | Everyone's predictions (after lock). |
| `/l/[slug]/rules` | `rules/page.tsx` | Scoring rules from the league config. |

## Data fetching pattern

- **Reads** happen in Server Components via `serverFetch("/path")`
  (`lib/server.ts`), which calls `auth().getToken()` and forwards the Clerk JWT.
- **Mutations** happen in `"use client"` components (`JoinLeague`,
  `CreateLeagueForm`, `PredictionsForm`) using `useAuth().getToken()` +
  `apiFetch()` (`lib/api.ts`), then `router.push`/`router.refresh`.
- `lib/types.ts` holds TypeScript interfaces that mirror the API JSON — **update
  them whenever an API shape changes.**

## Auth (Clerk)

- `app/layout.tsx` wraps everything in `<ClerkProvider localization={faIR}
  afterSignOutUrl="/">`.
- `src/proxy.ts` runs `clerkMiddleware` and `auth.protect()`s `/dashboard`, `/l/*`,
  `/leagues/*`.
- Header auth state uses `useUser()` (Clerk v7 has no `<SignedIn>`), plus
  `<UserButton/>` for the avatar/menu.

## Styling

- Plain CSS in `app/globals.css` (ported design tokens + component classes:
  `.card`, `.btn`, `.match`, `.table`, `.tab`, etc.) on top of the Tailwind import.
- RTL: `<html dir="rtl">`. Font: Vazirmatn via `next/font/google`.
- Dates: `fmtDateTime()` → Jalali. Numbers: `fa()` → Persian digits.

## Dev server

`pnpm dev` runs `next dev -p 3077 --webpack`. **Webpack is intentional** — the
Turbopack dev server crashed under load during development. Build uses the default.

## Conventions

- Persian text inline in JSX is fine (unlike the Python side, which centralizes
  strings in `consts.py`).
- Reuse existing CSS classes; keep the green/gold pitch theme.
- Keep `tsc --noEmit` clean — it is part of the test gate.
