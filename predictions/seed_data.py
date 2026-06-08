"""
Seed constants for the prediction league.

The **real** 2026 FIFA World Cup schedule (48 teams in groups A–L and all 104
matches with exact kickoff times) lives in `predictions/data/worldcup2026.json`
and is loaded by the `seed_worldcup2026` command. Only the competition's
name/slug live here, plus the small "test cup" used by `seed_test_tournament`.
"""

WC2026_NAME = "جام جهانی ۲۰۲۶"
WC2026_SLUG = "world-cup-2026"


# --------------------------------------------------------------------------- #
# Test tournament — a tiny competition with a COMPRESSED timeline (relative to
# "now") so every state can be exercised quickly: open / locked / finished.
# Used by the `seed_test_tournament` management command.
# --------------------------------------------------------------------------- #
TEST_CUP_NAME = "جام آزمایشی"
TEST_CUP_SLUG = "test-cup"

# (name_fa, code, flag)
TEST_CUP_TEAMS = [
    ("ایران", "IRN", "🇮🇷"),
    ("پرتغال", "POR", "🇵🇹"),
    ("آرژانتین", "ARG", "🇦🇷"),
    ("برزیل", "BRA", "🇧🇷"),
    ("فرانسه", "FRA", "🇫🇷"),
    ("اسپانیا", "ESP", "🇪🇸"),
    ("آلمان", "GER", "🇩🇪"),
    ("انگلیس", "ENG", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
]

# (home_idx, away_idx, minutes_from_now, home_score, away_score, stage)
#   minutes > 0  → in the future;  minutes < 0 → already played.
TEST_CUP_SCHEDULE = [
    (0, 1, 300, None, None, "GROUP"),   # +5h   → open
    (2, 3, 180, None, None, "GROUP"),   # +3h   → open
    (4, 5, 90, None, None, "GROUP"),    # +90m  → open
    (6, 7, 40, None, None, "GROUP"),    # +40m  → open (close to the 30-min lock)
    (0, 2, 10, None, None, "GROUP"),    # +10m  → LOCKED (inside the 30-min window)
    (1, 3, -45, 2, 1, "GROUP"),         # -45m  → finished 2-1
    (4, 6, -120, 0, 0, "GROUP"),        # -2h   → finished 0-0
    (5, 7, -240, 3, 1, "GROUP"),        # -4h   → finished 3-1
    (0, 4, 360, None, None, "F"),       # +6h   → open FINAL (×1.5 multiplier)
]
