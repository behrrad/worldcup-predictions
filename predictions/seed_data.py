"""
Seed constants for the prediction league.

The **real** 2026 FIFA World Cup schedule (48 teams in groups A–L and all 104
matches with exact kickoff times) lives in `predictions/data/worldcup2026.json`
and is loaded by the `seed_worldcup2026` command. Only the competition's
name/slug live here, plus the small "test cup" used by `seed_test_tournament`.
"""

WC2026_NAME = "جام جهانی ۲۰۲۶"
WC2026_SLUG = "world-cup-2026"

# A starter shortlist of players for the individual-award bonus questions
# (Golden Boot / Golden Ball). Loaded by `seed_player_candidates`, which links
# each to its team by code (leaving the team blank if that code isn't seeded).
# Curated from the tournament's Golden Boot / Golden Ball contenders (mid-2026);
# the league admin can add/remove names in the admin at any time.
# (Persian name, FIFA team code)
WC2026_PLAYER_CANDIDATES = [
    ("لیونل مسی", "ARG"),
    ("کیلیان امباپه", "FRA"),
    ("عثمان دمبله", "FRA"),
    ("مایکل اولیز", "FRA"),
    ("هری کین", "ENG"),
    ("جود بلینگام", "ENG"),
    ("ارلینگ هالند", "NOR"),
    ("میکل اویارزابال", "ESP"),
    ("اسماعیل صیباری", "MAR"),
    ("کوین دی بروینه", "BEL"),
    ("یوهان مانزامبی", "SUI"),
]


# --------------------------------------------------------------------------- #
# Test tournament — a tiny competition with a COMPRESSED timeline (relative to
# "now") so every state can be exercised quickly: open / locked / finished.
# Used by the `seed_test_tournament` management command.
# --------------------------------------------------------------------------- #
TEST_CUP_NAME = "جام آزمایشی"
TEST_CUP_SLUG = "test-cup"

# The seeded demo/test data deliberately uses a 30-minute lock (the app default
# is 0 = open until kickoff): without an early lock, the "locked but not yet
# kicked off" state below couldn't exist. The reveal-demo league is created
# with this value; the timelines' LOCKED matches assume it.
DEMO_LOCK_MINUTES = 30

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
    (6, 7, 40, None, None, "GROUP"),    # +40m  → open (close to the demo lock)
    (0, 2, 10, None, None, "GROUP"),    # +10m  → LOCKED (inside the demo lock window)
    (1, 3, -45, 2, 1, "GROUP"),         # -45m  → finished 2-1
    (4, 6, -120, 0, 0, "GROUP"),        # -2h   → finished 0-0
    (5, 7, -240, 3, 1, "GROUP"),        # -4h   → finished 3-1
    (0, 4, 360, None, None, "F"),       # +6h   → open FINAL (×1.5 multiplier)
]


# --------------------------------------------------------------------------- #
# Reveal-feature demo — a full, self-contained league (owner + members + their
# predictions) with one match in EVERY state, so the owner's "show others'
# predictions" toggle and the (demo's 30-minute) prediction lock can be exercised
# end-to-end in the running app. Used by the `seed_reveal_demo` command.
# --------------------------------------------------------------------------- #
REVEAL_DEMO_COMP_NAME = "دموی نمایش پیش‌بینی"
REVEAL_DEMO_COMP_SLUG = "reveal-demo"
REVEAL_DEMO_LEAGUE_NAME = "لیگ دموی نمایش"

# The owner (defaults to the project maintainer's real account so they can test
# as the league admin in the running app). Overridable via --owner-email.
REVEAL_DEMO_OWNER_EMAIL = "behrad@zenbase.ai"

# Bot members joined to the demo league. (email, display_name)
REVEAL_DEMO_MEMBERS = [
    ("alice+clerk_test@zenbase.ai", "Alice"),
    ("bob+clerk_test@zenbase.ai", "Bob"),
    ("carol+clerk_test@zenbase.ai", "Carol"),
]

# Reuse TEST_CUP_TEAMS; the four demo matches reference these indices.
# (home_idx, away_idx, minutes_from_now, home_score, away_score, stage)
REVEAL_DEMO_SCHEDULE = [
    (0, 1, 120, None, None, "GROUP"),   # +2h   → OPEN (predictions allowed)
    (2, 3, 10, None, None, "GROUP"),    # +10m  → LOCKED (inside the demo lock window)
    (4, 5, -20, None, None, "GROUP"),   # -20m  → STARTED (kicked off, no result yet)
    (6, 7, -120, 2, 1, "F"),            # -2h   → FINISHED 2-1 (final, ×1.5)
]

# Each member's prediction on each of the four matches above, in order.
# Chosen so the FINISHED match (آلمان 2-1 انگلیس) yields a spread of tiers:
#   owner 2-1 → exact · alice 3-2 → diff · bob 4-0 → winner · carol 0-1 → none-ish
# label "owner" is the --owner-email account; the rest match REVEAL_DEMO_MEMBERS.
REVEAL_DEMO_PREDICTIONS = {
    "owner": [(2, 1), (1, 1), (2, 0), (2, 1)],
    "alice+clerk_test@zenbase.ai": [(0, 0), (2, 2), (1, 1), (3, 2)],
    "bob+clerk_test@zenbase.ai": [(1, 2), (0, 1), (3, 1), (4, 0)],
    "carol+clerk_test@zenbase.ai": [(3, 1), (1, 0), (0, 0), (0, 1)],
}
