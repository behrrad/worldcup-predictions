"""
Seed data for the 2026 FIFA World Cup (48 teams, 12 groups A–L).

NOTE: group assignments, dates and kickoff times here are a *sensible starting
point* so the app is usable out of the box. Verify them against the official
draw/schedule and adjust freely in the admin panel (تیم‌ها / بازی‌ها).
"""

WC2026_NAME = "جام جهانی ۲۰۲۶"
WC2026_SLUG = "world-cup-2026"
WC2026_START = (2026, 6, 11)  # (year, month, day) — tournament start

# group -> [(name_fa, name_en, code, flag_emoji), ...]
WC2026_GROUPS = {
    "A": [
        ("کانادا", "Canada", "CAN", "🇨🇦"),
        ("کرواسی", "Croatia", "CRO", "🇭🇷"),
        ("مصر", "Egypt", "EGY", "🇪🇬"),
        ("عربستان", "Saudi Arabia", "KSA", "🇸🇦"),
    ],
    "B": [
        ("مکزیک", "Mexico", "MEX", "🇲🇽"),
        ("اروگوئه", "Uruguay", "URU", "🇺🇾"),
        ("نیجریه", "Nigeria", "NGA", "🇳🇬"),
        ("قطر", "Qatar", "QAT", "🇶🇦"),
    ],
    "C": [
        ("آمریکا", "United States", "USA", "🇺🇸"),
        ("کلمبیا", "Colombia", "COL", "🇨🇴"),
        ("غنا", "Ghana", "GHA", "🇬🇭"),
        ("تونس", "Tunisia", "TUN", "🇹🇳"),
    ],
    "D": [
        ("آرژانتین", "Argentina", "ARG", "🇦🇷"),
        ("ژاپن", "Japan", "JPN", "🇯🇵"),
        ("کامرون", "Cameroon", "CMR", "🇨🇲"),
        ("الجزایر", "Algeria", "ALG", "🇩🇿"),
    ],
    "E": [
        ("فرانسه", "France", "FRA", "🇫🇷"),
        ("مراکش", "Morocco", "MAR", "🇲🇦"),
        ("اکوادور", "Ecuador", "ECU", "🇪🇨"),
        ("ساحل عاج", "Ivory Coast", "CIV", "🇨🇮"),
    ],
    "F": [
        ("برزیل", "Brazil", "BRA", "🇧🇷"),
        ("سنگال", "Senegal", "SEN", "🇸🇳"),
        ("پرو", "Peru", "PER", "🇵🇪"),
        ("نروژ", "Norway", "NOR", "🇳🇴"),
    ],
    "G": [
        ("انگلیس", "England", "ENG", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
        ("ایران", "Iran", "IRN", "🇮🇷"),
        ("شیلی", "Chile", "CHI", "🇨🇱"),
        ("اوکراین", "Ukraine", "UKR", "🇺🇦"),
    ],
    "H": [
        ("اسپانیا", "Spain", "ESP", "🇪🇸"),
        ("کره جنوبی", "South Korea", "KOR", "🇰🇷"),
        ("پاراگوئه", "Paraguay", "PAR", "🇵🇾"),
        ("کاستاریکا", "Costa Rica", "CRC", "🇨🇷"),
    ],
    "I": [
        ("پرتغال", "Portugal", "POR", "🇵🇹"),
        ("ایتالیا", "Italy", "ITA", "🇮🇹"),
        ("لهستان", "Poland", "POL", "🇵🇱"),
        ("پاناما", "Panama", "PAN", "🇵🇦"),
    ],
    "J": [
        ("هلند", "Netherlands", "NED", "🇳🇱"),
        ("استرالیا", "Australia", "AUS", "🇦🇺"),
        ("صربستان", "Serbia", "SRB", "🇷🇸"),
        ("نیوزیلند", "New Zealand", "NZL", "🇳🇿"),
    ],
    "K": [
        ("آلمان", "Germany", "GER", "🇩🇪"),
        ("سوئیس", "Switzerland", "SUI", "🇨🇭"),
        ("اتریش", "Austria", "AUT", "🇦🇹"),
        ("اسکاتلند", "Scotland", "SCO", "🏴󠁧󠁢󠁳󠁣󠁴󠁿"),
    ],
    "L": [
        ("بلژیک", "Belgium", "BEL", "🇧🇪"),
        ("دانمارک", "Denmark", "DEN", "🇩🇰"),
        ("ترکیه", "Türkiye", "TUR", "🇹🇷"),
        ("ولز", "Wales", "WAL", "🏴󠁧󠁢󠁷󠁬󠁳󠁿"),
    ],
}

# Single round-robin pairings (by team index within a group of 4) across 3 matchdays.
GROUP_MATCHDAYS = [
    [(0, 1), (2, 3)],
    [(0, 2), (1, 3)],
    [(0, 3), (1, 2)],
]

# Knockout bracket shape: (stage_key, number_of_matches), in chronological order.
# Stage keys mirror predictions.consts.Stage.
KNOCKOUT_ROUNDS = [
    ("R32", 16),
    ("R16", 8),
    ("QF", 4),
    ("SF", 2),
    ("TP", 1),
    ("F", 1),
]
