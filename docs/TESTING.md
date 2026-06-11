# Testing workflow

This is the safety net that lets anyone change the code **without breaking existing
behavior**. The rule is simple:

> **Run the tests before you start and after every change. Add a test for every new
> function or rule. Never merge with a failing test or a type error.**

## The test gate (run all of this)

```bash
# 1. Backend logic & API — fast (in-memory SQLite, mocked Clerk, no network)
.venv/bin/python manage.py test --settings=config.settings_test

# 2. Frontend type safety — the contract between UI and API
cd frontend && pnpm exec tsc --noEmit

# 3. (optional, before release) Frontend production build
cd frontend && pnpm build
```

If all three are green, the core logic is sound.

## What is covered today

Backend tests live in `accounts/tests/` and `predictions/tests/` (63 tests).

| File | Covers |
|------|--------|
| `predictions/tests/test_scoring.py` | **The scoring engine.** Every tier (exact / diff / winner / participation / none), draws, knockout multipliers, custom league config, recompute on result entry/change/clear, leaderboard ranking & ties. |
| `predictions/tests/test_models.py` | Invite-code generation, unicode slugs, per-stage multipliers, `is_finished`/status sync, the **prediction lock window** (open/closed/at-kickoff with the zero-minute default/finished). |
| `predictions/tests/test_api.py` | Auth required (401), create/join/list leagues, owner-only invite code, non-member 404, **prediction lock enforcement** server-side, update-in-place, negative rejection, leaderboard, match-detail reveal-after-lock. |
| `predictions/tests/test_seed.py` | The 2026 seed command loading the **real** schedule: 48 teams, 72 group + 32 knockout matches, real opener (Mexico v South Africa), Iran in group G, idempotent reload **preserving predictions/results**, `--reset` rebuild, and invalid-file rejection (no partial writes). Plus the `seed_test_tournament` compressed-timeline command. |
| `accounts/tests/test_auth.py` | Clerk auth class (no header / non-Bearer / valid / invalid, all mocked) and user-sync from claims vs Clerk API. |

## Test design notes

- **`config/settings_test.py`** swaps Postgres for in-memory SQLite, sets dummy
  Clerk env, and uses fast password hashing — so tests are hermetic and ~0.1s.
- **Clerk is always mocked** in tests (`unittest.mock.patch`) — no network, no real
  tokens. The auth bridge is tested in isolation in `test_auth.py`.
- **API tests** use DRF's `APIClient.force_authenticate(user=...)` to bypass the
  Clerk layer and exercise the view/business logic directly.
- **Factories** (`predictions/tests/factories.py`) build users/competitions/teams/
  matches/leagues with one call — use them in new tests.

## How to add tests when you build a feature

| You changed… | Add/extend… |
|--------------|-------------|
| Scoring rule or `scoring.py` | `test_scoring.py` — assert the exact points/tier for the new case, including a knockout-multiplier case. |
| A model field/method, lock logic | `test_models.py`. |
| An API endpoint | `test_api.py` — happy path, auth required, and at least one rejection/edge case. |
| The seed data/command | `test_seed.py`. |
| The Clerk integration | `test_auth.py` (keep it mocked). |
| A frontend API shape | update `frontend/src/lib/types.ts`; keep `tsc --noEmit` clean. |

### Pattern for a new backend test

```python
from django.test import TestCase
from .factories import make_competition, make_league, make_match

class MyFeatureTests(TestCase):
    def test_it(self):
        comp = make_competition()
        league = make_league(comp)
        # ... arrange, act, assert exact expected values
```

### Pattern for a new API test

```python
from rest_framework.test import APITestCase, APIClient
from django.urls import reverse
from .factories import make_user, make_competition

class MyEndpointTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=make_user())
    def test_endpoint(self):
        res = self.client.get(reverse("api_..."))
        self.assertEqual(res.status_code, 200)
```

## Manual / end-to-end verification

Automated tests cover logic; for full-stack confidence also:

1. Start Postgres (Supabase), Django (`:8001`), Next.js (`:3077`).
2. Sign up (Clerk **test emails** like `you+clerk_test@example.com` accept the
   bypass code `424242` on development instances).
3. Create a league → copy the invite code → join from another account.
4. Submit a prediction before lock; confirm it cannot be changed after lock.
5. In `/admin`, enter a match result → confirm the leaderboard updates.

## Continuous integration

`.github/workflows/ci.yml` runs the gate on every push/PR to `main`:

- **backend** job — `pip install -r requirements.txt`, then
  `python manage.py check` + `test` with `--settings=config.settings_test`
  (in-memory SQLite + mocked Clerk → no database service, no secrets).
- **frontend** job — `pnpm install --frozen-lockfile` then `pnpm exec tsc --noEmit`.

Both jobs run in parallel and require no repository secrets.
