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
[ { "rank": 1, "name": "علی", "total": 17.0, "played": 3, "exact_count": 1, "is_me": true }, ... ]
```

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
