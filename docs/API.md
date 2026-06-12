# API reference

Base URL: `http://127.0.0.1:8001/api` · Defined in `predictions/api_urls.py`,
implemented in `predictions/api_views.py`.

**Auth:** every endpoint requires `Authorization: Bearer <Clerk session JWT>`
(see [ARCHITECTURE.md](ARCHITECTURE.md)). Unauthenticated → `401`. Not a member of
the requested league → `404`. League `slug` may be non-ASCII (Persian) and is
URL-encoded by the client.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/me/` | Current user `{email, display_name, public_name}` |
| GET | `/competitions/` | Active competitions `[{id, name, slug}]` |
| GET | `/leagues/` | My leagues `[{slug, name, competition, role, is_owner, member_count}]` |
| POST | `/leagues/` | Create a league → league detail (201) |
| POST | `/leagues/join/` | Join via `{invite_code}` → `{slug, name, created}` |
| GET | `/leagues/<slug>/` | League detail + scoring config |
| GET | `/leagues/<slug>/matches/` | All matches with my prediction/points/lock state |
| POST | `/leagues/<slug>/predictions/` | Submit predictions → `{saved}` |
| GET | `/leagues/<slug>/leaderboard/` | Ranked standings |
| GET | `/leagues/<slug>/matches/<id>/` | One match + everyone's predictions (after lock) |
| GET | `/live/` | In-play scores of matches being played right now (see below) |

### Live scores — GET `/live/`

Display-only in-play state (score, minute, status) for every match currently
being played, across active competitions. Lazily refreshed from a free live
provider (ESPN, falling back to Varzesh3) at most once per
`consts.LIVE_REFRESH_SECONDS` regardless of how many clients poll — and not at
all when no match could be live. The same `live` object is embedded per match
in `/leagues/<slug>/matches/`. Live data never feeds the scoring engine; an
officially finished match never appears here.

Calling this endpoint also lazily **finalizes results**: when a match looks
over (the provider reports full time, or kickoff is `RESULTS_PENDING_AFTER_HOURS`
past) but has no official result yet, the football-data.org sync runs behind
an atomic claim on `Competition.results_checked_at` (at most once per
`consts.RESULTS_SYNC_SECONDS`), so the official result — and everyone's
points — land minutes after the final whistle with no cron and no manual
entry. Manual entry in the admin still works and wins.

```json
{
  "checked_at": "2026-06-12T20:45:00+00:00",
  "matches": [
    {
      "id": 3, "kickoff": "2026-06-12T19:00:00+00:00",
      "home_team": { "name": "کانادا", ... }, "away_team": { "name": "بوسنی و هرزگوین", ... },
      "status": "LIVE",              // LIVE | HT | FT
      "status_label": "زنده",
      "minute": "65",                // only while in play, e.g. "45+4"
      "home": 0, "away": 1
    }
  ]
}
```

## Shapes

### POST `/leagues/`
```json
{ "name": "لیگ من", "competition_id": 1, "description": "" }
```
Returns the league detail object (below) with `invite_code` populated (you are owner).

### League detail — GET `/leagues/<slug>/`
```json
{
  "slug": "...", "name": "...", "description": "...",
  "competition": { "name": "...", "slug": "..." },
  "member_count": 3, "is_owner": true, "role": "OWNER",
  "invite_code": "ABCD2345",            // null unless you are the owner
  "scoring": {
    "points_exact": 10, "points_correct_diff": 7,
    "points_correct_winner": 5, "points_participation": 2,
    "lock_minutes": 0,
    "stage_multipliers": [ { "stage": "GROUP", "label": "مرحله گروهی", "multiplier": 1.0 }, ... ]
  }
}
```

### Match (in `/matches/` and `/matches/<id>/`)
```json
{
  "id": 1, "stage": "GROUP", "stage_label": "مرحله گروهی",
  "kickoff": "2026-06-11T18:00:00+03:30",
  "home_team": { "id": 1, "name": "کانادا", "code": "CAN", "flag": "🇨🇦", "group": "A" },
  "away_team": { ... },
  "home_score": null, "away_score": null,
  "is_finished": false, "is_open": true, "can_predict": true,
  "lock_time": "2026-06-11T17:30:00+03:30",
  "my_prediction": { "home": 2, "away": 1 },   // or null
  "my_points": null, "tier": null, "tier_label": null
}
```

### Submit predictions — POST `/leagues/<slug>/predictions/`
```json
{ "predictions": [ { "match_id": 1, "home": 2, "away": 1 }, ... ] }
```
Server-side rules (enforced regardless of client): only matches that are **open**
(before lock) and have both teams set are saved; negatives/invalid entries are
ignored. Returns `{ "saved": <count> }`.

### Leaderboard — GET `/leagues/<slug>/leaderboard/`
```json
{
  "is_live": true,                      // a match is in play: live_* differ from official
  "rows": [
    {
      "rank": 1, "name": "علی", "total": 17.0, "played": 3, "exact_count": 1, "is_me": true,
      "live_rank": 2, "live_total": 17.0, "live_points": 0.0
    }
  ]
}
```
`live_*` is the provisional view: the current score of in-play matches played
as if it were the final result (`live_points` is the delta on top of `total`).
Display-only — `MatchScore` rows still come exclusively from official results.
When nothing is live, `is_live` is false and `live_*` mirror the official fields.

### Match detail — GET `/leagues/<slug>/matches/<id>/`
```json
{
  "match": { ...Match... },
  "revealed": true,                      // false until the match locks
  "lock_time": "...",
  "predictions": [ { "name": "...", "home": 2, "away": 1, "points": 10.0, "tier_label": "نتیجهٔ دقیق", "is_me": false } ]
}
```
Others' predictions are hidden (`predictions: []`, `revealed: false`) until lock,
so nobody can copy.

## Adding an endpoint
See AGENTS.md §6. Always add a matching test in `predictions/tests/test_api.py`.
