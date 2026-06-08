"""
Central constants for the prediction league.

Everything that is a fixed value or a piece of UI text lives here — scoring
points, stage keys and their Persian labels, default multipliers, the lock
window, membership roles, and all reusable strings/messages. Code elsewhere
imports from this module instead of hardcoding literals, so tuning the league
or editing wording happens in one place.
"""
import re
from decimal import Decimal


# --------------------------------------------------------------------------- #
# Match stages
# --------------------------------------------------------------------------- #
class Stage:
    GROUP = "GROUP"
    ROUND_OF_32 = "R32"
    ROUND_OF_16 = "R16"
    QUARTER = "QF"
    SEMI = "SF"
    THIRD_PLACE = "TP"
    FINAL = "F"


STAGE_LABELS = {
    Stage.GROUP: "مرحله گروهی",
    Stage.ROUND_OF_32: "مرحله یک‌شانزدهم نهایی",
    Stage.ROUND_OF_16: "مرحله یک‌هشتم نهایی",
    Stage.QUARTER: "مرحله یک‌چهارم نهایی",
    Stage.SEMI: "مرحله نیمه‌نهایی",
    Stage.THIRD_PLACE: "رده‌بندی (مقام سوم)",
    Stage.FINAL: "فینال",
}

# Display / DB order of the stages.
STAGE_ORDER = [
    Stage.GROUP,
    Stage.ROUND_OF_32,
    Stage.ROUND_OF_16,
    Stage.QUARTER,
    Stage.SEMI,
    Stage.THIRD_PLACE,
    Stage.FINAL,
]

STAGE_CHOICES = [(key, STAGE_LABELS[key]) for key in STAGE_ORDER]

# Stages that count as "elimination" rounds (they get a multiplier > 1 by default).
KNOCKOUT_STAGES = {
    Stage.ROUND_OF_32,
    Stage.ROUND_OF_16,
    Stage.QUARTER,
    Stage.SEMI,
    Stage.THIRD_PLACE,
    Stage.FINAL,
}


# --------------------------------------------------------------------------- #
# Scoring — default points per outcome tier (editable per league in the admin)
# --------------------------------------------------------------------------- #
DEFAULT_POINTS_EXACT = 10          # exact score, e.g. predicted 2-1, actual 2-1
DEFAULT_POINTS_CORRECT_DIFF = 7    # right winner AND right goal difference
DEFAULT_POINTS_CORRECT_WINNER = 5  # right winner only (wrong margin)
DEFAULT_POINTS_PARTICIPATION = 2   # a prediction was submitted but missed all of the above
POINTS_NO_PREDICTION = 0           # no prediction submitted in time

# Default multipliers per stage.
DEFAULT_GROUP_MULTIPLIER = Decimal("1.0")
DEFAULT_KNOCKOUT_MULTIPLIER = Decimal("1.5")

DEFAULT_STAGE_MULTIPLIERS = {
    stage: (DEFAULT_KNOCKOUT_MULTIPLIER if stage in KNOCKOUT_STAGES
            else DEFAULT_GROUP_MULTIPLIER)
    for stage in STAGE_ORDER
}

# How many minutes before kickoff predictions lock.
DEFAULT_LOCK_MINUTES = 30

# Whether other members' predictions are revealed once a match locks. The league
# owner can turn this off (per league) to keep everyone's picks private — names
# and participation still show, but the actual predicted scores never appear.
DEFAULT_REVEAL_PREDICTIONS = True


# --------------------------------------------------------------------------- #
# Scoring tiers (used to label *why* a prediction earned its points)
# --------------------------------------------------------------------------- #
class Tier:
    EXACT = "EXACT"
    DIFF = "DIFF"
    WINNER = "WINNER"
    PARTICIPATION = "PARTICIPATION"
    NONE = "NONE"


TIER_LABELS = {
    Tier.EXACT: "نتیجهٔ دقیق",
    Tier.DIFF: "برندهٔ درست + اختلاف گل",
    Tier.WINNER: "برندهٔ درست",
    Tier.PARTICIPATION: "شرکت در پیش‌بینی",
    Tier.NONE: "بدون پیش‌بینی",
}

TIER_CHOICES = [(key, label) for key, label in TIER_LABELS.items()]


# --------------------------------------------------------------------------- #
# Match status
# --------------------------------------------------------------------------- #
class MatchStatus:
    SCHEDULED = "SCHEDULED"
    FINISHED = "FINISHED"


MATCH_STATUS_LABELS = {
    MatchStatus.SCHEDULED: "برنامه‌ریزی‌شده",
    MatchStatus.FINISHED: "پایان‌یافته",
}

MATCH_STATUS_CHOICES = [(k, v) for k, v in MATCH_STATUS_LABELS.items()]


# --------------------------------------------------------------------------- #
# Membership roles
# --------------------------------------------------------------------------- #
class Role:
    OWNER = "OWNER"
    MEMBER = "MEMBER"


ROLE_LABELS = {
    Role.OWNER: "مدیر مسابقه",
    Role.MEMBER: "شرکت‌کننده",
}

ROLE_CHOICES = [(k, v) for k, v in ROLE_LABELS.items()]


# --------------------------------------------------------------------------- #
# Invite codes
# --------------------------------------------------------------------------- #
INVITE_CODE_LENGTH = 8
# Unambiguous alphabet (no 0/O, 1/I/L) so codes are easy to read and share.
INVITE_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


# --------------------------------------------------------------------------- #
# Slugs (readable, shareable league/competition URLs)
# --------------------------------------------------------------------------- #
# League names are Persian, so slugify(..., allow_unicode=True) used to produce
# Persian slugs that percent-encode into gibberish when shared
# (/l/%D9%84%DB%8C%DA%AF-...). Instead we transliterate the name to Latin letters
# first, then slugify, so a league called «لیگ دوستان» lives at /l/lig-dustan.
#
# This is *transliteration* (sound → Latin letters), not translation (meaning).
# Persian is an abjad — short vowels aren't written — so the result is an
# approximate, consonant-leaning romanization. Where a letter can be a vowel or a
# consonant we lean toward the vowel reading (و→u, ی→i, ع→a), which reads better
# for typical league names. The map is intentionally simple and position-blind so
# the output is predictable and testable.
FA_TO_LATIN = {
    # Alef family
    "ا": "a", "آ": "a", "أ": "a", "إ": "a", "ٱ": "a", "ى": "a",
    # Hamza carriers
    "ء": "", "ئ": "y", "ؤ": "v",
    # Consonants
    "ب": "b", "پ": "p", "ت": "t", "ث": "s", "ج": "j", "چ": "ch",
    "ح": "h", "خ": "kh", "د": "d", "ذ": "z", "ر": "r", "ز": "z",
    "ژ": "zh", "س": "s", "ش": "sh", "ص": "s", "ض": "z", "ط": "t",
    "ظ": "z", "ع": "a", "غ": "gh", "ف": "f", "ق": "gh",
    "ک": "k", "ك": "k", "گ": "g", "ل": "l", "م": "m", "ن": "n",
    "و": "u", "ه": "h", "ة": "h", "ی": "i", "ي": "i",
    # Persian & Arabic-Indic digits
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    # Joiners, tatweel and harakat (vowel marks) are dropped
    "‌": "", "‍": "", "ـ": "",
    "ً": "", "ٌ": "", "ٍ": "", "َ": "",
    "ُ": "", "ِ": "", "ّ": "", "ْ": "",
}
# Used when a name transliterates to nothing (e.g. only emoji/punctuation).
SLUG_FALLBACK_LEAGUE = "league"
SLUG_FALLBACK_COMPETITION = "competition"


# --------------------------------------------------------------------------- #
# Results export (per-league .xlsx download, key-gated)
# --------------------------------------------------------------------------- #
# Each league owns a URL-safe export key — secrets.token_urlsafe(EXPORT_KEY_BYTES)
# — that lets anyone holding it download the league's results spreadsheet.
EXPORT_KEY_BYTES = 24          # -> a 32-character URL-safe token
EXPORT_KEY_MAX_LENGTH = 64     # generous DB column width for the token

# Spreadsheet layout (mirrors the shared league template):
#   row 1  -> league title in column A + each member's name in their first column
#   row 2  -> each member's running total
#   row 3+ -> one row per match
# Columns A-D hold the fixture (home, away, actual home, actual away); every
# member then owns EXPORT_COLS_PER_MEMBER columns (predicted home, predicted
# away, points) starting at EXPORT_FIRST_MEMBER_COL.
EXPORT_TITLE_ROW = 1
EXPORT_TOTAL_ROW = 2
EXPORT_FIRST_MATCH_ROW = 3
EXPORT_COL_HOME = 1            # A
EXPORT_COL_AWAY = 2           # B
EXPORT_COL_ACTUAL_HOME = 3    # C
EXPORT_COL_ACTUAL_AWAY = 4    # D
EXPORT_FIRST_MEMBER_COL = 5   # E
EXPORT_COLS_PER_MEMBER = 3    # predicted home, predicted away, points

EXPORT_SHEET_TITLE_MAX = 31   # Excel's hard limit on a worksheet tab name
EXPORT_SHEET_TITLE_FALLBACK = "Export"
EXPORT_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
EXPORT_FILENAME_TEMPLATE = "{slug}.xlsx"
EXPORT_FILENAME_FALLBACK = "results.xlsx"  # ASCII name for clients that ignore filename*
# Content-Disposition that survives a non-ASCII (Persian) slug via RFC 5987.
EXPORT_CONTENT_DISPOSITION = "attachment; filename=\"{ascii}\"; filename*=UTF-8''{encoded}"
# Relative API path of the public download (frontend prepends the API base).
EXPORT_PATH_TEMPLATE = "/api/export/{key}.xlsx"


# --------------------------------------------------------------------------- #
# Frontend paths (relative to settings.FRONTEND_URL)
# --------------------------------------------------------------------------- #
# A league's page in the Next.js app lives at /l/<slug> (frontend/src/app/l/[slug]).
LEAGUE_DETAIL_PATH = "/l/{slug}"


# --------------------------------------------------------------------------- #
# Model verbose names
# --------------------------------------------------------------------------- #
V_COMPETITION = "تورنمنت (رویداد واقعی)"
V_COMPETITION_PLURAL = "تورنمنت‌ها"
V_TEAM = "تیم"
V_TEAM_PLURAL = "تیم‌ها"
V_MATCH = "بازی"
V_MATCH_PLURAL = "بازی‌ها"
V_LEAGUE = "مسابقهٔ پیش‌بینی"
V_LEAGUE_PLURAL = "مسابقه‌های پیش‌بینی"
V_MEMBERSHIP = "عضویت"
V_MEMBERSHIP_PLURAL = "عضویت‌ها"
V_PREDICTION = "پیش‌بینی"
V_PREDICTION_PLURAL = "پیش‌بینی‌ها"
V_MATCHSCORE = "امتیاز بازی"
V_MATCHSCORE_PLURAL = "امتیازهای بازی"


# --------------------------------------------------------------------------- #
# Field labels
# --------------------------------------------------------------------------- #
L_NAME = "نام"
L_SLUG = "نامک (آدرس)"
L_DESCRIPTION = "توضیحات"
L_START_DATE = "تاریخ شروع"
L_IS_ACTIVE = "فعال"
L_CREATED_AT = "زمان ساخت"
L_UPDATED_AT = "زمان ویرایش"

L_TEAM_NAME_FA = "نام تیم (فارسی)"
L_TEAM_NAME_EN = "نام تیم (انگلیسی)"
L_TEAM_CODE = "کد سه‌حرفی"
L_TEAM_FLAG = "پرچم (ایموجی)"
L_TEAM_GROUP = "گروه"

L_COMPETITION = "تورنمنت"
L_STAGE = "مرحله"
L_HOME_TEAM = "تیم میزبان"
L_AWAY_TEAM = "تیم میهمان"
L_KICKOFF = "زمان شروع بازی"
L_HOME_SCORE = "گل میزبان"
L_AWAY_SCORE = "گل میهمان"
L_STATUS = "وضعیت"
L_MATCH_NUMBER = "شمارهٔ بازی"
L_VENUE = "ورزشگاه"
L_HOME_LABEL = "جایگاه میزبان (مرحلهٔ حذفی)"
L_AWAY_LABEL = "جایگاه میهمان (مرحلهٔ حذفی)"

L_LEAGUE = "مسابقهٔ پیش‌بینی"
L_OWNER = "مدیر"
L_INVITE_CODE = "کد دعوت"
L_EXPORT_KEY = "کلید خروجی نتایج"
L_LOCK_MINUTES = "بستن پیش‌بینی (دقیقه قبل از شروع)"
L_REVEAL_PREDICTIONS = "نمایش پیش‌بینی دیگران پس از بسته‌شدن"
L_POINTS_EXACT = "امتیاز نتیجهٔ دقیق"
L_POINTS_CORRECT_DIFF = "امتیاز برنده + اختلاف گل"
L_POINTS_CORRECT_WINNER = "امتیاز برندهٔ درست"
L_POINTS_PARTICIPATION = "امتیاز شرکت در پیش‌بینی"
L_MULT_GROUP = "ضریب مرحلهٔ گروهی"
L_MULT_R32 = "ضریب یک‌شانزدهم نهایی"
L_MULT_R16 = "ضریب یک‌هشتم نهایی"
L_MULT_QF = "ضریب یک‌چهارم نهایی"
L_MULT_SF = "ضریب نیمه‌نهایی"
L_MULT_TP = "ضریب ردهبندی"
L_MULT_FINAL = "ضریب فینال"

L_USER = "کاربر"
L_ROLE = "نقش"
L_JOINED_AT = "زمان عضویت"
L_MEMBERSHIP = "عضویت"
L_MATCH = "بازی"
L_PREDICTED_HOME = "پیش‌بینی گل میزبان"
L_PREDICTED_AWAY = "پیش‌بینی گل میهمان"
L_POINTS = "امتیاز"
L_TIER = "نوع امتیاز"
L_COMPUTED_AT = "زمان محاسبه"

# Help texts
HELP_INVITE_CODE = "این کد را با دوستانتان به اشتراک بگذارید تا به مسابقه بپیوندند."
HELP_EXPORT_KEY = "با این کلید هرکسی می‌تواند فایل اکسل نتایج این مسابقه را دانلود کند."
HELP_LOCK_MINUTES = "پیش‌بینی هر بازی این تعداد دقیقه پیش از شروع بسته می‌شود."
HELP_REVEAL_PREDICTIONS = (
    "اگر روشن باشد، پس از بسته‌شدن هر بازی پیش‌بینی دیگران برای همهٔ اعضا "
    "نمایش داده می‌شود. اگر خاموش باشد، پیش‌بینی‌ها همیشه خصوصی می‌مانند."
)
HELP_SLUG = "اگر خالی بماند به‌صورت خودکار ساخته می‌شود."


# --------------------------------------------------------------------------- #
# Flash / UI messages
# --------------------------------------------------------------------------- #
MSG_LEAGUE_CREATED = "مسابقه ساخته شد. کد دعوت: {code}"
MSG_JOINED_LEAGUE = "به مسابقهٔ «{name}» پیوستید."
MSG_ALREADY_MEMBER = "شما از قبل عضو این مسابقه هستید."
MSG_INVALID_INVITE = "کد دعوت نامعتبر است."
MSG_PREDICTION_SAVED = "پیش‌بینی شما ذخیره شد."
MSG_PREDICTION_LOCKED = "زمان پیش‌بینی این بازی به پایان رسیده است."
MSG_NOT_A_MEMBER = "شما عضو این مسابقه نیستید."
MSG_PREDICTIONS_NOTHING = "هیچ پیش‌بینی قابل ثبتی وجود نداشت."

# Generic UI strings (used across templates via views/context where needed)
BRAND_NAME = "پیش‌بینی جام جهانی"


# --------------------------------------------------------------------------- #
# Admin panel
# --------------------------------------------------------------------------- #
ADMIN_INDEX_TITLE = "پنل مدیریت"
ADMIN_SECTION_SCORING = "تنظیمات امتیازدهی"
ADMIN_SECTION_MULTIPLIERS = "ضریب مراحل حذفی"
ADMIN_SECTION_GENERAL = "اطلاعات کلی"
ACTION_RECOMPUTE_MATCH = "محاسبهٔ دوبارهٔ امتیازِ بازی‌های انتخاب‌شده"
ACTION_RECOMPUTE_LEAGUE = "محاسبهٔ دوبارهٔ کل امتیازهای مسابقه"
ACTION_REGENERATE_EXPORT_KEY = "ساخت دوبارهٔ کلید خروجی (کلید قبلی باطل می‌شود)"
MSG_ADMIN_RECOMPUTED = "{n} امتیاز دوباره محاسبه شد."
MSG_ADMIN_EXPORT_KEYS_REGENERATED = "{n} کلید خروجی دوباره ساخته شد."
COL_SCORE = "نتیجه"
COL_MEMBER_COUNT = "تعداد اعضا"
COL_PREDICTION = "پیش‌بینی"


# --------------------------------------------------------------------------- #
# In-app admin (manual result entry)
# --------------------------------------------------------------------------- #
MSG_ADMIN_ONLY = "این بخش فقط برای مدیر در دسترس است."
MSG_INVALID_RESULT = "نتیجهٔ واردشده نامعتبر است."
# Changing a league's settings is restricted to its owner (the league "admin").
MSG_OWNER_ONLY = "فقط مدیر مسابقه می‌تواند تنظیمات آن را تغییر دهد."
MSG_EXPORT_INVALID_KEY = "کلید خروجی نامعتبر است."


# --------------------------------------------------------------------------- #
# Rate limiting (DRF throttling)
# --------------------------------------------------------------------------- #
# Scope names referenced by the throttle classes in predictions/throttles.py
# and by DEFAULT_THROTTLE_RATES in config/settings.py. (No anon scope: every
# endpoint requires auth, so anonymous requests never reach throttling.)
THROTTLE_SCOPE_USER = "user"
THROTTLE_SCOPE_PREDICT = "predict"
THROTTLE_SCOPE_JOIN = "league-join"
THROTTLE_SCOPE_EXPORT = "export"   # the one anonymous endpoint (key-gated .xlsx download)

# Default request rates per scope (DRF "<number>/<period>" syntax). These are
# the defaults; each is overridable via the matching env var in settings.py.
THROTTLE_RATE_USER = "300/min"     # authenticated requests (per user) — baseline
THROTTLE_RATE_PREDICT = "60/min"   # prediction submits (per user)
THROTTLE_RATE_JOIN = "20/min"      # league-join attempts (per user)
THROTTLE_RATE_EXPORT = "30/min"    # results-export downloads (per client IP, anonymous)


# --------------------------------------------------------------------------- #
# Knockout bracket-slot labels (Persian)
# --------------------------------------------------------------------------- #
# The schedule JSON stores English placeholders for knockout matches whose teams
# aren't decided yet (e.g. "Group A Winner", "Match 73 Winner"). bracket_label_fa
# turns those into Persian so the UI shows a meaningful slot instead of "؟".
BRACKET_GROUP_WINNER = "صدرنشین گروه {group}"
BRACKET_GROUP_RUNNER_UP = "نایب‌قهرمان گروه {group}"
BRACKET_GROUP_THIRD = "تیم سوم از گروه‌های {groups}"
BRACKET_MATCH_WINNER = "برندهٔ بازی {n}"
BRACKET_MATCH_LOSER = "بازندهٔ بازی {n}"
BRACKET_UNKNOWN = "نامشخص"  # empty/undecided slot

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def to_fa_digits(value) -> str:
    """Render a number with Persian (Eastern Arabic) digits."""
    return str(value).translate(_FA_DIGITS)


def bracket_label_fa(label: str) -> str:
    """Translate an English bracket-slot label to Persian.

    Returns BRACKET_UNKNOWN for an empty label and echoes anything that doesn't
    match a known pattern (so a new format degrades gracefully instead of
    raising).
    """
    if not label:
        return BRACKET_UNKNOWN
    if m := re.fullmatch(r"Group ([A-L]) Winner", label):
        return BRACKET_GROUP_WINNER.format(group=m.group(1))
    if m := re.fullmatch(r"Group ([A-L]) Runner-up", label):
        return BRACKET_GROUP_RUNNER_UP.format(group=m.group(1))
    if m := re.fullmatch(r"Group ([A-L](?:/[A-L])*) 3rd Place", label):
        return BRACKET_GROUP_THIRD.format(groups=m.group(1))
    if m := re.fullmatch(r"Match (\d+) Winner", label):
        return BRACKET_MATCH_WINNER.format(n=to_fa_digits(m.group(1)))
    if m := re.fullmatch(r"Match (\d+) Loser", label):
        return BRACKET_MATCH_LOSER.format(n=to_fa_digits(m.group(1)))
    return label


# --------------------------------------------------------------------------- #
# Results sync (football-data.org) — used by the sync_results command
# --------------------------------------------------------------------------- #
FOOTBALL_DATA_BASE_URL = "https://api.football-data.org/v4"
FOOTBALL_DATA_WC_CODE = "WC"             # football-data's FIFA World Cup code
FOOTBALL_DATA_TIMEOUT = 15               # seconds
FOOTBALL_DATA_FINISHED = "FINISHED"      # the API match status we act on
FOOTBALL_DATA_USER_AGENT = "worldcup-predictions/1.0"  # default urllib UA is blocked
FOOTBALL_DATA_TOKEN_HEADER = "X-Auth-Token"
FOOTBALL_DATA_TOKEN_ENV = "FOOTBALL_DATA_API_TOKEN"
# A source result only updates a local match if its kickoff is within this many
# hours of the API's date — guards against same-team results from another
# season/source being written onto the 2026 schedule.
FOOTBALL_DATA_MATCH_WINDOW_HOURS = 48

MSG_SYNC_NO_TOKEN = (
    "توکن دسترسی football-data.org تنظیم نشده است "
    "(متغیر محیطی FOOTBALL_DATA_API_TOKEN یا گزینهٔ --token)."
)
MSG_SYNC_HTTP_ERROR = "خطا در دریافت نتایج از football-data.org: {error}"
MSG_SYNC_BAD_JSON = "پاسخ نامعتبر (غیر-JSON) از football-data.org دریافت شد."
MSG_SYNC_NO_COMPETITION = "تورنمنت «{slug}» پیدا نشد؛ ابتدا seed_worldcup2026 را اجرا کنید."
MSG_SYNC_DRY_RUN = "حالت آزمایشی فعال است؛ هیچ تغییری ذخیره نشد."
MSG_SYNC_UPDATED = "به‌روزرسانی بازی {n}: {home} {hs}–{as_} {away}"
MSG_SYNC_UNMATCHED = "بدون تطبیق در برنامهٔ محلی: {home} – {away} ({date})"
MSG_SYNC_DONE = (
    "همگام‌سازی نتایج انجام شد: {updated} به‌روزرسانی، {unchanged} بدون تغییر، "
    "{unmatched} بدون تطبیق (از {total} بازی پایان‌یافتهٔ دریافتی)."
)

