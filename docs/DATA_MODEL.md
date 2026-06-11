# Data model

All models are in `predictions/models.py` (plus `accounts/models.py` for `User`).
Field labels and choices come from `consts.py` (see the conventions in AGENTS.md).

## Entities

```
Competition 1──* Team
Competition 1──* Match  (home_team, away_team → Team)
Competition 1──* League
League      1──* Membership *──1 User
Membership  1──* Prediction *──1 Match
Membership  1──* MatchScore *──1 Match
```

### User (`accounts.User`)
Custom user; **email is the login** (no username). Key fields:
- `email` (unique), `display_name`, `clerk_id` (unique, links to the Clerk account).
- `public_name` property → display name or email prefix (used on leaderboards).

### Competition
The real-world event (e.g. «جام جهانی ۲۰۲۶»). `name`, `slug` (unicode), `start_date`,
`is_active`. Owns Teams and Matches. **Multiple leagues can predict one Competition.**

### Team
`competition`, `name_fa`, `name_en`, `code`, `flag_emoji`, `group`. Unique per
`(competition, name_fa)`.

### Match
A fixture in a Competition.
- `stage` — one of `consts.Stage` (GROUP, R32, R16, QF, SF, TP/third-place, F/final).
- `home_team`, `away_team` (nullable — knockout slots are TBD until the bracket resolves).
- `kickoff` (tz-aware), `home_score`, `away_score` (nullable until played), `status`.
- **`is_finished`** ≡ both scores entered. `save()` auto-syncs `status`.
- **`is_open_for(lock_minutes, now)`** — can a prediction still be submitted? False if
  finished or `now >= kickoff - lock_minutes`.
- **`lock_time(lock_minutes)`** = `kickoff - lock_minutes`.

### League (the friends' "tournament")
References a Competition; carries its **own scoring config** (admin-editable):
- `owner`, `invite_code` (auto, unambiguous alphabet), `slug` (unicode), `members` (M2M via Membership).
- Points: `points_exact`, `points_correct_diff`, `points_correct_winner`, `points_participation`.
- `lock_minutes` (default 0 — predictions stay open until kickoff; a positive value locks that many minutes earlier).
- Per-stage multipliers: `multiplier_group`, `multiplier_r32`, `multiplier_r16`,
  `multiplier_qf`, `multiplier_sf`, `multiplier_tp`, `multiplier_final`.
- `multiplier_for(stage)` returns the right one.

### Membership
A user's seat in a league. `role` (OWNER/MEMBER), `joined_at`. Unique per `(league, user)`.

### Prediction
**Per `(membership, match)`** — i.e. a user predicts separately *in each league*.
`predicted_home`, `predicted_away`. Unique per `(membership, match)`.

> Design note: predictions are per-membership (not global per user). This keeps each
> league independent — its own lock time, its own scoring, no cross-league coupling.

### MatchScore
The computed points a member earned on a match. `points` (Decimal), `tier`
(`consts.Tier`), `computed_at`. Unique per `(membership, match)`. Rebuilt by the
recompute signal; **never edit by hand** — change the Match result or league config
and let it recompute.

## Stages & multipliers

`consts.STAGE_ORDER` defines the order; `consts.KNOCKOUT_STAGES` marks elimination
rounds. Group = ×1.0, knockout = ×1.5 by default — all overridable per league.

## Migrations

Standard Django migrations in `*/migrations/`. After changing a model:
`python manage.py makemigrations && python manage.py migrate`.
