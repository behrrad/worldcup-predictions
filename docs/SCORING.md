# Scoring

All logic is in `predictions/scoring.py`. All numbers are **per-league settings**
(defaults in `predictions/consts.py`), editable in the admin. Tests:
`predictions/tests/test_scoring.py`.

## The rules

For each finished match, a prediction earns the **single highest tier** that
applies, then the result is multiplied by the match's **stage multiplier**:

| Tier (`consts.Tier`) | Condition | Default points |
|----------------------|-----------|----------------|
| `EXACT` | exact score (e.g. predict 2–1, actual 2–1) | **10** |
| `DIFF`  | right winner **and** right goal difference (predict 2–1, actual 3–2) | **7** |
| `WINNER`| right winner only (right side wins, wrong margin) | **5** |
| `PARTICIPATION` | a prediction was submitted but matched none of the above | **2** |
| `NONE` | no prediction submitted in time | **0** |

```
final_points = base_points(tier) × league.multiplier_for(match.stage)
```

Default multipliers: group **×1.0**, every knockout round **×1.5** (each round has
its own field, so you can later make them differ).

### Worked examples (default config)

| Predicted | Actual | Stage | Tier | Points |
|-----------|--------|-------|------|--------|
| 2–1 | 2–1 | group | EXACT | 10 × 1.0 = **10** |
| 2–1 | 3–2 | group | DIFF | 7 × 1.0 = **7** |
| 1–0 | 3–1 | group | WINNER | 5 × 1.0 = **5** |
| 0–2 | 2–1 | group | PARTICIPATION | 2 × 1.0 = **2** |
| 2–1 | 2–1 | final | EXACT | 10 × 1.5 = **15** |
| 0–3 | 2–1 | semi  | PARTICIPATION | 2 × 1.5 = **3** |
| 0–0 | 2–2 | group | DIFF (draw, same diff 0) | **7** |

## The algorithm

```python
def base_tier(ph, pa, ah, aa):
    if (ph, pa) == (ah, aa):            return EXACT
    if (ph - pa) == (ah - aa):          return DIFF      # same diff ⇒ same winner+margin
    if sign(ph - pa) == sign(ah - aa):  return WINNER     # sign: 1/0/-1 (0 = draw)
    return PARTICIPATION                                  # a prediction exists but is wrong
```

`score_prediction(league, match, prediction)`:
- returns `None` if the match has no result yet,
- `(Decimal("0.00"), NONE)` if `prediction is None`,
- else `(base × multiplier, tier)` quantized to 2 decimals.

## Recompute & leaderboard

- **`recompute_match_scores(match)`** — for every league on the match's competition,
  upsert a `MatchScore` for each member. Called automatically by the `post_save`
  signal on `Match` (`predictions/signals.py`) and by the admin action / the
  `compute_scores` command. Clearing a result deletes its scores.
- **`recompute_league_scores(league)`** — rebuild one league (use after changing its
  scoring config; there's an admin action for it).
- **`leaderboard(league)`** — totals per member, ranked, with standard
  competition ranking for ties (equal totals share a rank). Returns rows with
  `rank, name, total, played, exact_count`.

## Changing the rules safely

1. Adjust defaults in `consts.py` and/or the per-league fields in the admin.
2. If you change the **algorithm** (`base_tier`/`score_prediction`), update
   `predictions/tests/test_scoring.py` to lock in the new behavior.
3. Run `recompute` (admin action or `python manage.py compute_scores`) so existing
   `MatchScore` rows reflect the new logic.
