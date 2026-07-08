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

# --------------------------------------------------------------------------- #
# Mid-tournament knockout multiplier boost (owner opt-in)
# --------------------------------------------------------------------------- #
# From the quarter-finals onward a league owner may opt in to raise the knockout
# multiplier to this value (from the DEFAULT_KNOCKOUT_MULTIPLIER of 1.5). The
# decision is recorded once per league so the prompt is shown a single time; it
# only affects not-yet-scored matches, so it's non-retroactive at QF stage.
BOOST_TARGET_MULTIPLIER = Decimal("2.0")

# Stages the boost applies to (quarter-finals and everything after).
BOOST_STAGES = [Stage.QUARTER, Stage.SEMI, Stage.THIRD_PLACE, Stage.FINAL]


class BoostDecision:
    PENDING = "PENDING"     # owner hasn't answered the prompt yet
    ACCEPTED = "ACCEPTED"   # owner opted in — multipliers raised to 2×
    DECLINED = "DECLINED"   # owner declined — multipliers stay at 1.5×


BOOST_DECISION_LABELS = {
    BoostDecision.PENDING: "در انتظار تصمیم",
    BoostDecision.ACCEPTED: "پذیرفته‌شده",
    BoostDecision.DECLINED: "ردشده",
}
BOOST_DECISION_CHOICES = [(k, v) for k, v in BOOST_DECISION_LABELS.items()]
BOOST_DECISION_MAX_LENGTH = 8

# The two values the PATCH endpoint accepts for the `boost_decision` action.
BOOST_ACTION_ACCEPT = "accept"
BOOST_ACTION_DECLINE = "decline"

L_BOOST_DECISION = "تصمیم دربارهٔ ضریب ۲برابری مراحل حذفی"

# How many minutes before kickoff predictions lock. 0 = open until kickoff.
DEFAULT_LOCK_MINUTES = 0

# Whether other members' predictions are revealed once a match locks. The league
# owner can turn this off (per league) to keep everyone's picks private — names
# and participation still show, but the actual predicted scores never appear.
DEFAULT_REVEAL_PREDICTIONS = True


# --------------------------------------------------------------------------- #
# Fun stats (the «آمار جالب» tab)
# --------------------------------------------------------------------------- #
# A "best buddies" pair only qualifies once it has at least this many shared
# predictions. Without a floor, any pair that matched on a single shared game
# shows up at 100%, drowning out genuinely similar members.
FUN_STATS_MIN_BUDDY_MATCHES = 5

# The "active participant" bar: a member counts as active once they've predicted
# at least this fraction of the finished matches so far. Gates both the average
# leaderboard (scoring.live_leaderboard) and the best-buddies pairing — stats
# that are meaningless for someone who has barely played.
MIN_FINISHED_PARTICIPATION_RATIO = 0.5


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
# Knockout penalty shootouts (who advances when a game is level at 120')
# --------------------------------------------------------------------------- #
# A knockout match still level at the end of 120' (regular + extra time) is
# decided on penalties; the shootout winner advances. Predictions are judged on
# the 120' score, so a member who predicts a draw in a knockout also picks who
# they think will go through (Prediction.predicted_advancer), and the real
# outcome is stored in Match.penalty_winner. Both use these HOME/AWAY values
# (empty = not a shootout / not predicted).
class Advancer:
    NONE = ""        # not decided on penalties, or no advancer picked
    HOME = "HOME"    # the home side advances / is predicted to advance
    AWAY = "AWAY"    # the away side advances / is predicted to advance


ADVANCER_LABELS = {
    Advancer.HOME: "تیم میزبان",
    Advancer.AWAY: "تیم میهمان",
}
ADVANCER_CHOICES = [(k, v) for k, v in ADVANCER_LABELS.items()]
ADVANCER_VALUES = (Advancer.HOME, Advancer.AWAY)
ADVANCER_MAX_LENGTH = 4   # "HOME" / "AWAY"


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
    # Alef family. «ى» (U+0649, alef maksura) is the long-ā ending of Arabic-origin
    # names common in Persian (موسى→musa, مصطفى→mostafa, عیسى→isa), so it maps to
    # "a", not to a yeh — see test_known_examples.
    "ا": "a", "آ": "a", "أ": "a", "إ": "a", "ٱ": "a", "ى": "a",
    # Hamza carriers
    "ء": "", "ئ": "y", "ؤ": "v",
    # Consonants
    "ب": "b", "پ": "p", "ت": "t", "ث": "s", "ج": "j", "چ": "ch",
    "ح": "h", "خ": "kh", "د": "d", "ذ": "z", "ر": "r", "ز": "z",
    "ژ": "zh", "س": "s", "ش": "sh", "ص": "s", "ض": "z", "ط": "t",
    "ظ": "z", "ع": "a", "غ": "gh", "ف": "f", "ق": "gh",
    "ک": "k", "ك": "k", "گ": "g", "ل": "l", "م": "m", "ن": "n",
    "و": "u", "ه": "h", "ة": "h", "ۀ": "e", "ی": "i", "ي": "i",
    # Persian & Arabic-Indic digits
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    # Joiners, tatweel, harakat (vowel marks) and combining hamza/maddah are dropped
    "‌": "", "‍": "", "ـ": "",
    "ً": "", "ٌ": "", "ٍ": "", "َ": "",
    "ُ": "", "ِ": "", "ّ": "", "ْ": "",
    "ٓ": "", "ٔ": "", "ٕ": "",
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

# --- Spreadsheet styling (mirrors the shared league template's colour scheme) --
# Colours are ARGB-friendly hex (no leading '#'); openpyxl accepts 6-digit RGB.
EXPORT_STYLE_RTL = True                  # Persian content reads right-to-left
EXPORT_LABEL_TOTAL = "مجموع امتیاز"       # row-2 label over the fixture columns

EXPORT_COLOR_TITLE_BG = "800B02"         # deep maroon banner (A1)
EXPORT_COLOR_TITLE_FG = "E9C84A"         # gold title text
EXPORT_COLOR_HEADER_BG = "BA9920"        # gold member-name headers (row 1)
EXPORT_COLOR_HEADER_FG = "2B2B2B"
EXPORT_COLOR_TOTAL_BG = "EFE2B8"         # pale gold standings band (row 2)
EXPORT_COLOR_TOTAL_FG = "5A3A00"
EXPORT_COLOR_TEAM_BG = "FFC000"          # amber home/away team cells
EXPORT_COLOR_TEAM_FG = "373737"
EXPORT_COLOR_RESULT_BG = "002060"        # navy actual-score cells
EXPORT_COLOR_RESULT_FG = "FFFFFF"
EXPORT_COLOR_PRED_BG = "FFF7E6"          # light cream predicted-score cells
EXPORT_COLOR_PRED_FG = "373737"
EXPORT_COLOR_POINTS_BG = "BFBFBF"        # grey points cells
EXPORT_COLOR_POINTS_FG = "1A1A1A"
EXPORT_COLOR_BORDER = "D9D9D9"           # light grid lines

EXPORT_TITLE_FONT_SIZE = 14
EXPORT_TOTAL_FONT_SIZE = 13
EXPORT_HEADER_FONT_SIZE = 11
EXPORT_BODY_FONT_SIZE = 11
EXPORT_POINTS_FONT_SIZE = 9

EXPORT_WIDTH_TEAM = 16                    # columns A, B (team names)
EXPORT_WIDTH_RESULT = 4.5                 # columns C, D (actual score)
EXPORT_WIDTH_PRED = 4.5                   # each member's predicted home/away
EXPORT_WIDTH_POINTS = 6                   # each member's points
EXPORT_TITLE_ROW_HEIGHT = 22


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
L_COUNT_FOR_SCORING = "محاسبه در امتیازها"
L_MATCH_NUMBER = "شمارهٔ بازی"
L_VENUE = "ورزشگاه"
L_HOME_LABEL = "جایگاه میزبان (مرحلهٔ حذفی)"
L_AWAY_LABEL = "جایگاه میهمان (مرحلهٔ حذفی)"
L_PENALTY_WINNER = "صعودکننده با پنالتی"

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

L_LIVE_HOME_SCORE = "گل میزبان (زنده)"
L_LIVE_AWAY_SCORE = "گل میهمان (زنده)"
L_LIVE_MINUTE = "دقیقهٔ بازی (زنده)"
L_LIVE_STATUS = "وضعیت زنده"
L_LIVE_UPDATED_AT = "زمان به‌روزرسانی زنده"
L_LIVE_CHECKED_AT = "آخرین بررسی نتایج زنده"
L_RESULTS_CHECKED_AT = "آخرین همگام‌سازی خودکار نتایج"

L_USER = "کاربر"
L_ROLE = "نقش"
L_JOINED_AT = "زمان عضویت"
L_MEMBERSHIP = "عضویت"
L_MATCH = "بازی"
L_PREDICTED_HOME = "پیش‌بینی گل میزبان"
L_PREDICTED_AWAY = "پیش‌بینی گل میهمان"
L_PREDICTED_ADVANCER = "پیش‌بینی صعودکننده (پنالتی)"
L_POINTS = "امتیاز"
L_TIER = "نوع امتیاز"
L_COMPUTED_AT = "زمان محاسبه"

# Help texts
HELP_INVITE_CODE = "این کد را با دوستانتان به اشتراک بگذارید تا به مسابقه بپیوندند."
HELP_EXPORT_KEY = "با این کلید هرکسی می‌تواند فایل اکسل نتایج این مسابقه را دانلود کند."
HELP_LOCK_MINUTES = (
    "پیش‌بینی هر بازی این تعداد دقیقه پیش از شروع بسته می‌شود. "
    "۰ یعنی تا لحظهٔ شروع بازی باز می‌ماند."
)
HELP_REVEAL_PREDICTIONS = (
    "اگر روشن باشد، پس از بسته‌شدن هر بازی پیش‌بینی دیگران برای همهٔ اعضا "
    "نمایش داده می‌شود. اگر خاموش باشد، پیش‌بینی‌ها همیشه خصوصی می‌مانند."
)
HELP_SLUG = "اگر خالی بماند به‌صورت خودکار ساخته می‌شود."
HELP_COUNT_FOR_SCORING = (
    "اگر خاموش باشد، این بازی در امتیازها و جدول رده‌بندی محاسبه نمی‌شود؛ "
    "پیش‌بینی‌ها و نتیجه حفظ می‌شوند ولی امتیازی به همراه ندارند."
)


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

# --- Admin theme (django-unfold) ---------------------------------------------
# Verbose plurals for the two auth models, so the themed sidebar can label them
# in Persian alongside the prediction models (which already have V_* names).
V_USER_PLURAL = "کاربران"
V_GROUP_PLURAL = "گروه‌ها"
# Sidebar section headings grouping the models in the Unfold navigation.
ADMIN_NAV_GROUP_PREDICTIONS = "پیش‌بینی"
ADMIN_NAV_GROUP_ACCOUNTS = "حساب‌ها"
# Short label shown above the table-filter rail.
ADMIN_FILTER_TITLE = "فیلترها"


# --------------------------------------------------------------------------- #
# In-app admin (manual result entry)
# --------------------------------------------------------------------------- #
MSG_ADMIN_ONLY = "این بخش فقط برای مدیر در دسترس است."
MSG_INVALID_RESULT = "نتیجهٔ واردشده نامعتبر است."
# Changing a league's settings is restricted to its owner (the league "admin").
MSG_OWNER_ONLY = "فقط مدیر مسابقه می‌تواند تنظیمات آن را تغییر دهد."
MSG_EXPORT_INVALID_KEY = "کلید خروجی نامعتبر است."
MSG_BOOST_ACTION_INVALID = "مقدار تصمیم ضریب نامعتبر است."


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

# A knockout slot points at the winner or the loser of an earlier match. These
# are the two "kind"s a "Match N Winner"/"Match N Loser" label resolves to (also
# the group(2) captured by BRACKET_MATCH_SLOT_RE); the bracket auto-advance reads
# them to know whether a slot takes the advancing or the eliminated side.
BRACKET_WINNER = "Winner"
BRACKET_LOSER = "Loser"
# Match-referencing slot label, e.g. "Match 73 Winner" -> (73, "Winner").
BRACKET_MATCH_SLOT_RE = re.compile(r"Match (\d+) (Winner|Loser)")

# The two team sides of a match, as the model's field-name stems (home_team /
# away_team, home_score / away_score). Used to iterate a match's slots generically.
SIDE_HOME = "home"
SIDE_AWAY = "away"

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def to_fa_digits(value) -> str:
    """Render a number with Persian (Eastern Arabic) digits."""
    return str(value).translate(_FA_DIGITS)


def parse_bracket_slot(label: str):
    """Parse a "Match N Winner"/"Match N Loser" slot label into
    ``(source_match_number: int, kind)`` where kind is BRACKET_WINNER/LOSER, or
    None for an empty label or any other placeholder (group slots, real teams).
    """
    if not label:
        return None
    m = BRACKET_MATCH_SLOT_RE.fullmatch(label.strip())
    if not m:
        return None
    return int(m.group(1)), m.group(2)


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
    if m := BRACKET_MATCH_SLOT_RE.fullmatch(label):
        n = to_fa_digits(m.group(1))
        template = (BRACKET_MATCH_WINNER if m.group(2) == BRACKET_WINNER
                    else BRACKET_MATCH_LOSER)
        return template.format(n=n)
    return label


# --------------------------------------------------------------------------- #
# Matchday recap (the animated end-of-day story; see predictions/recap.py)
# --------------------------------------------------------------------------- #
# A "matchday" is a calendar day — in the schedule's timezone — on which at
# least one match finished. The recap groups, ranks and compares that day's
# results. We use the host region's timezone (not the viewer's): World Cup 2026
# is played across North America, and US-Pacific is the westernmost host zone,
# so a day's whole slate of kickoffs lands on one calendar date there. Grouping
# by Tehran instead would split a single FIFA matchday across midnight (an
# Americas evening kickoff is the early hours of the next day in Tehran).
RECAP_MATCHDAY_TZ = "America/Los_Angeles"
RECAP_DATE_FORMAT = "%Y-%m-%d"
# How many members the closing "podium" card shows (current standings top N).
RECAP_PODIUM_SIZE = 3


# --------------------------------------------------------------------------- #
# Live scores (in-play state shown on the site; never feeds the scoring engine)
# --------------------------------------------------------------------------- #
# In-play state of a match as reported by a live provider. Stored on Match in
# the live_* fields, which are written with queryset.update() so Match.save()
# (which would mark the match FINISHED and recompute points) never runs on
# live data. The official result still arrives via sync_results/admin only.
class LiveStatus:
    NONE = ""          # no live information
    LIVE = "LIVE"      # ball in play (live_minute carries the clock)
    HALFTIME = "HT"    # between the halves
    FULL_TIME = "FT"   # provider says it ended; official result may lag behind


LIVE_STATUS_LABELS = {
    LiveStatus.LIVE: "زنده",
    LiveStatus.HALFTIME: "بین دو نیمه",
    LiveStatus.FULL_TIME: "پایان بازی",
}

LIVE_STATUS_CHOICES = [(k, v) for k, v in LIVE_STATUS_LABELS.items()]

LIVE_MINUTE_MAX_LENGTH = 12     # e.g. "45+4", "90+12"
LIVE_STATUS_MAX_LENGTH = 4

# How long a fetched live snapshot stays fresh. While any match is in its live
# window, at most one upstream request happens per this many seconds — no
# matter how many users are polling.
LIVE_REFRESH_SECONDS = 45
# Upstream is only consulted when a match could plausibly be in play: kickoff
# between LIVE_WINDOW_BEFORE_HOURS in the past and LIVE_WINDOW_AFTER_MINUTES in
# the future (covers 90' + break + stoppage + knockout extra time/penalties).
LIVE_WINDOW_BEFORE_HOURS = 3
LIVE_WINDOW_AFTER_MINUTES = 5
# A provider result only applies to a local match whose kickoff is within this
# window of the provider's date (same guard idea as the results sync).
LIVE_MATCH_WINDOW_HOURS = 6
# An in-play match the provider stopped reporting keeps its live state this
# long before being cleared — one flaky partial response must not blank an
# ongoing match, but a dead feed can't leave a stuck "زنده" badge either.
LIVE_STALE_CLEAR_SECONDS = 600

LIVE_FETCH_TIMEOUT = 8          # seconds, per provider
# The default "Python-urllib" UA is rejected by some CDNs (same gotcha as
# accounts/clerk.py and sync_results), so send a real one.
LIVE_USER_AGENT = "worldcup-predictions/1.0"

# Provider identifiers (recorded for logging/debugging only).
LIVE_PROVIDER_ESPN = "espn"
LIVE_PROVIDER_VARZESH3 = "varzesh3"

# ESPN's (unofficial, keyless) World Cup scoreboard. One request returns every
# match of the current scoreboard day with score, clock and status.
ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
)
# ESPN status.type.state values
ESPN_STATE_PRE = "pre"
ESPN_STATE_IN = "in"
ESPN_STATE_POST = "post"
ESPN_STATUS_HALFTIME = "STATUS_HALFTIME"
ESPN_HOME = "home"
ESPN_AWAY = "away"

# Varzesh3's (unofficial, keyless) livescore feed — the fallback provider.
# Returns every league with matches today, all sports mixed (football is
# sport == 1); teams carry Persian names only, so matching uses name_fa.
VARZESH3_LIVESCORE_URL = "https://web-api.varzesh3.com/v2.0/livescore/today"
VARZESH3_SPORT_FOOTBALL = 1


# Varzesh3 match status enum (extracted from their web bundle).
class Varzesh3Status:
    NOT_STARTED = 1
    LIVE = 2
    FINISHED = 7


# Varzesh3 reports halftime as status LIVE with this statusTitle and an empty
# liveTime, so the title string is the only halftime signal.
VARZESH3_HALFTIME_TITLE = "پایان نیمه"


# --------------------------------------------------------------------------- #
# Results sync (football-data.org) — used by the sync_results command
# --------------------------------------------------------------------------- #
FOOTBALL_DATA_BASE_URL = "https://api.football-data.org/v4"
FOOTBALL_DATA_WC_CODE = "WC"             # football-data's FIFA World Cup code
FOOTBALL_DATA_TIMEOUT = 15               # seconds
FOOTBALL_DATA_FINISHED = "FINISHED"      # the API match status we act on
# score.duration values + the shootout winner enum. A PENALTY_SHOOTOUT match's
# score.fullTime *includes* the shootout goals (regularTime 1-1 + penalties 6-5
# → fullTime 7-6), so the 120' draw we score against is fullTime − penalties and
# the side that advances comes from score.winner.
FOOTBALL_DATA_PENALTY = "PENALTY_SHOOTOUT"
FOOTBALL_DATA_WINNER_HOME = "HOME_TEAM"
FOOTBALL_DATA_WINNER_AWAY = "AWAY_TEAM"
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

# --------------------------------------------------------------------------- #
# Lazy results finalization — official result fetched once a match looks over
# --------------------------------------------------------------------------- #
# When a match looks over (live provider reports full time, or kickoff is long
# enough past) but has no official result yet, the live API endpoint lazily
# runs the football-data.org sync behind an atomic claim on
# Competition.results_checked_at (same pattern as the live refresh): at most
# one upstream request per this many seconds, none when nothing is pending.
RESULTS_SYNC_SECONDS = 180
# A match counts as "pending finalization" from this long after kickoff even
# without a live FT signal (covers a dead live feed) ...
RESULTS_PENDING_AFTER_HOURS = 2
# ... and stops being chased after this long — by then it's the admin's call.
RESULTS_PENDING_MAX_HOURS = 24


# --------------------------------------------------------------------------- #
# Telegram reminders (predictions/telegram.py)
# --------------------------------------------------------------------------- #
# A Telegram bot DMs members who haven't predicted a match yet: a once-a-day
# morning digest of today's open matches, plus a final nudge shortly before
# kickoff. Linking is one-tap: the website hands out a deep link carrying a
# short, single-use token; tapping "Start" in the bot sends /start <token>,
# which we resolve to the user and store their chat id.
#
# Everything is env-gated (no token configured -> every send/poll is a silent
# no-op), uses urllib (no new dependency), and follows the same atomic-claim,
# no-cron philosophy as live.py / results_sync.py. The periodic work is driven
# by an external scheduler (GitHub Actions) hitting the secret-gated tick
# endpoint; that one call also refreshes live scores and finalizes results, so
# reminders and auto-finalization both work even when no user is on the site.

# Env var names (read in config/settings.py).
TELEGRAM_BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
TELEGRAM_BOT_USERNAME_ENV = "TELEGRAM_BOT_USERNAME"
TASK_TRIGGER_KEY_ENV = "TASK_TRIGGER_KEY"

# -- Email (Resend) --------------------------------------------------------- #
# Announcement/transactional email via Resend's HTTP API. Env-gated: with no
# RESEND_API_KEY the sender is a no-op (the feature ships dark), so nothing is
# emailed until the key + a verified from-address are configured.
RESEND_API_KEY_ENV = "RESEND_API_KEY"
DEFAULT_FROM_EMAIL_ENV = "DEFAULT_FROM_EMAIL"
RESEND_API_URL = "https://api.resend.com/emails"
EMAIL_USER_AGENT = "worldcup-predictions/1.0"  # default urllib UA is blocked
EMAIL_FETCH_TIMEOUT = 10               # seconds, per API call
EMAIL_FROM_FALLBACK = "World Cup <onboarding@resend.dev>"
# Placeholder addresses minted for users without a real Clerk email; never mail
# these (see accounts/clerk.py). Match on the domain suffix.
EMAIL_PLACEHOLDER_SUFFIX = "@users.noreply.clerk"

# Telegram Bot API.
TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"
TELEGRAM_METHOD_SEND_MESSAGE = "sendMessage"
TELEGRAM_METHOD_GET_UPDATES = "getUpdates"
TELEGRAM_PARSE_MODE = "HTML"
TELEGRAM_FETCH_TIMEOUT = 10           # seconds, per API call
TELEGRAM_USER_AGENT = "worldcup-predictions/1.0"  # default urllib UA is blocked
TELEGRAM_GET_UPDATES_LIMIT = 100
# Only message updates from a private chat can link an account.
TELEGRAM_CHAT_TYPE_PRIVATE = "private"
TELEGRAM_START_COMMAND = "/start"
TELEGRAM_STOP_COMMAND = "/stop"

# One-tap linking: the deep link the website hands out, and the single-use
# token it carries. Telegram's start payload only allows [A-Za-z0-9_-] (max 64
# chars), so the token is token_urlsafe(...) (~22 chars), not a signed blob.
TELEGRAM_DEEP_LINK = "https://t.me/{username}?start={token}"
TELEGRAM_LINK_TOKEN_BYTES = 16
TELEGRAM_LINK_TOKEN_MAX_AGE_SECONDS = 3600   # a link token is valid for one hour

# getUpdates is polled (no public webhook) behind an atomic claim on the
# singleton TelegramState row: at most one drain per this many seconds, however
# many requests arrive (the connect page polls while waiting for the link).
TELEGRAM_POLL_SECONDS = 2

# When reminders fire.
TELEGRAM_NUDGE_LEAD_MINUTES = 30      # final nudge this long before kickoff
# The morning digest goes out at/after this local hour (settings.TIME_ZONE),
# once per day, listing the day's still-open matches the member hasn't predicted.
TELEGRAM_DIGEST_HOUR = 9

# NotificationLog dedup-key prefixes (one row = one thing already sent).
# The first two are the prediction reminders; the rest are the live match-event
# DMs (telegram.run_match_events), each fired at most once per (user, kind, key).
class NotifyKind:
    DIGEST = "DIGEST"       # dedup key: the local date, e.g. "2026-06-14"
    NUDGE = "NUDGE"         # dedup key: the match id
    KICKOFF = "KICKOFF"     # dedup key: the match id
    GOAL = "GOAL"           # dedup key: "<match id>:<home>-<away>" (one per scoreline)
    HALFTIME = "HALFTIME"   # dedup key: the match id
    SECOND_HALF = "SECONDHALF"  # dedup key: the match id
    FULLTIME = "FULLTIME"   # dedup key: the match id
    ANNOUNCE = "ANNOUNCE"   # dedup key: the announcement's campaign key


NOTIFY_KIND_LABELS = {
    NotifyKind.DIGEST: "خلاصهٔ روزانه",
    NotifyKind.NUDGE: "یادآوری پیش از بازی",
    NotifyKind.KICKOFF: "شروع بازی",
    NotifyKind.GOAL: "گل",
    NotifyKind.HALFTIME: "پایان نیمهٔ اول",
    NotifyKind.SECOND_HALF: "شروع نیمهٔ دوم",
    NotifyKind.FULLTIME: "پایان بازی",
    NotifyKind.ANNOUNCE: "اطلاعیه",
}
NOTIFY_KIND_CHOICES = [(k, v) for k, v in NOTIFY_KIND_LABELS.items()]

# Live match-event kinds, in the order events are emitted within one tick.
NOTIFY_MATCH_EVENT_KINDS = (
    NotifyKind.KICKOFF, NotifyKind.GOAL, NotifyKind.HALFTIME,
    NotifyKind.SECOND_HALF, NotifyKind.FULLTIME,
)

NOTIFY_KIND_MAX_LENGTH = 12   # widest kind is "SECONDHALF" (10)
NOTIFY_DEDUP_KEY_MAX_LENGTH = 40
# A goal dedup key carries the scoreline: "<match id>:<home>-<away>".
NOTIFY_GOAL_KEY = "{match_id}:{home}-{away}"
# Only emit live match-event DMs for matches whose kickoff is within this many
# hours of now (so newly opted-in members aren't spammed with older matches, and
# the FULL_TIME catch-up window stays bounded).
TELEGRAM_EVENT_WINDOW_HOURS = 4
# A "kickoff" DM only fires this soon after the real kickoff — long enough for the
# next cron tick to catch it, short enough that a late opt-in / late live feed
# doesn't get a stale "kickoff!" for a match already well underway.
TELEGRAM_KICKOFF_GRACE_MINUTES = 20
# The second-half DM fires once the live clock is back in play in this minute
# range (the half resumes at 46'); the upper bound keeps it from firing stale,
# deep into the half, when a match is only first observed mid-second-half.
SECOND_HALF_MINUTE = 46
SECOND_HALF_MINUTE_MAX = 60

# -- Bot replies (sent to the user in the chat) ----------------------------- #
TG_REPLY_LINKED = (
    "✅ حساب تلگرام شما با موفقیت به «{name}» متصل شد.\n"
    "از این پس یادآوری بازی‌هایی که هنوز پیش‌بینی نکرده‌ای را همین‌جا می‌فرستیم."
)
TG_REPLY_LINK_INVALID = (
    "این لینک اتصال نامعتبر یا منقضی شده است. لطفاً از صفحهٔ «پروفایل من» در سایت "
    "دوباره روی «اتصال به تلگرام» بزن."
)
TG_REPLY_START_NO_TOKEN = (
    "سلام! 👋 برای اتصال حساب، از صفحهٔ «پروفایل من» در سایت روی دکمهٔ "
    "«اتصال به تلگرام» بزن."
)
TG_REPLY_STOPPED = (
    "🔕 یادآوری‌های تلگرام خاموش شد. هر وقت خواستی از سایت دوباره روشنش کن."
)
TG_REPLY_STOP_NOT_LINKED = "این گفتگو به هیچ حسابی متصل نیست."

# -- Reminder messages ------------------------------------------------------ #
# parse_mode=HTML, so the footer link is a real anchor and team names are escaped.
TG_DIGEST_TITLE = "🗓 <b>بازی‌های امروز که هنوز پیش‌بینی نکرده‌ای:</b>"
TG_NUDGE_TITLE = "⏰ <b>کمتر از {minutes} دقیقه تا شروع بازی!</b> هنوز پیش‌بینی نکرده‌ای:"
# One fixture line. {time} is the local kickoff (HH:MM, Persian digits).
TG_MATCH_LINE = "• {home} {hflag} - {aflag} {away} — ساعت {time}"
TG_REMINDER_FOOTER = "همین حالا ثبت کن 👇\n<a href=\"{url}\">{url}</a>"

# Frontend path the reminder links to (cross-league, so the dashboard).
TELEGRAM_REMINDER_PATH = "/dashboard"

# -- 2× knockout-boost announcement ----------------------------------------- #
# Idempotency keys (NotificationLog dedup_key): one Telegram DM and one email per
# member for this campaign. The two channels use distinct keys so both can fire
# to the same member without colliding on the (user, kind, dedup_key) guard.
ANNOUNCE_2X_CAMPAIGN = "2026-qf-2x"
ANNOUNCE_2X_EMAIL_CAMPAIGN = "2026-qf-2x-email"
# Telegram broadcast (parse_mode=HTML). {url} is the site link.
TG_ANNOUNCE_2X = (
    "📣 <b>خبر مهم درباره‌ی امتیازها!</b>\n\n"
    "از مرحلهٔ یک‌چهارم نهایی به بعد، امتیاز بازی‌های حذفی <b>۲ برابر</b> می‌شود "
    "(به‌جای ۱٫۵ برابر). یعنی پیش‌بینی درست بازی‌های بزرگِ پیش‌رو ارزش بیشتری دارد.\n\n"
    "اگر مدیر یک مسابقه هستی، در صفحهٔ مسابقه‌ات این تغییر را تأیید کن تا برای اعضا فعال شود.\n"
    "<a href=\"{url}\">{url}</a>"
)
# Email broadcast (plain text; {name} is the member's display name).
EMAIL_ANNOUNCE_2X_SUBJECT = "ضریب امتیاز مراحل حذفی ۲ برابر شد ⚽️"
EMAIL_ANNOUNCE_2X_BODY = (
    "سلام {name}،\n\n"
    "از مرحلهٔ یک‌چهارم نهایی به بعد، امتیاز بازی‌های حذفی ۲ برابر می‌شود "
    "(به‌جای ۱٫۵ برابر). پیش‌بینی درستِ بازی‌های بزرگِ پیش‌رو حالا ارزش بیشتری دارد.\n\n"
    "اگر مدیر یک مسابقه هستی، در صفحهٔ مسابقه‌ات این تغییر را تأیید کن تا برای اعضا فعال شود:\n"
    "{url}\n\n"
    "موفق باشی!"
)

# -- Live match-event messages (telegram.run_match_events) ------------------- #
# Each DM is a title line, a fixture/score line, then a personalized line built
# from the member's own prediction(s). parse_mode=HTML, so team names are escaped.
TG_EVENT_KICKOFF_TITLE = "🟢 <b>سوت شروع شد!</b>"
# {clock} is " (دقیقهٔ X)" when a live minute is known, else empty.
TG_EVENT_GOAL_TITLE = "⚽️ <b>گُل!</b>{clock}"
TG_EVENT_HALFTIME_TITLE = "⏸ <b>پایان نیمهٔ اول</b>"
TG_EVENT_SECONDHALF_TITLE = "🟢 <b>شروع نیمهٔ دوم!</b>"
TG_EVENT_FULLTIME_TITLE = "🏁 <b>پایان بازی</b>"
# Fixture line without a score (kickoff) and with one (goal/HT/FT).
TG_EVENT_FIXTURE_LINE = "{hflag} {home} - {away} {aflag}"
TG_EVENT_SCORE_LINE = "{hflag} {home} <b>{hs} - {as}</b> {away} {aflag}"
# How a live minute is rendered into {clock} above (Persian digits supplied).
TG_EVENT_GOAL_CLOCK = " (دقیقهٔ {minute})"
# Personalized lines (omitted entirely when the member didn't predict).
TG_EVENT_YOUR_PICK = "پیش‌بینی تو: <b>{picks}</b>"
TG_EVENT_PICK_JOIN = "، "           # joins distinct picks across the member's leagues
TG_EVENT_ON_TRACK = "✅ تا اینجا دقیقاً مطابق پیش‌بینی‌ات!"
TG_EVENT_POINTS = "🎯 از این بازی <b>{points}</b> امتیاز گرفتی!"
TG_EVENT_POINTS_NONE = "این بار امتیازی به دست نیاوردی."
TG_EVENT_NO_PICK = "این بازی را پیش‌بینی نکرده بودی."
# A single predicted scoreline, Persian digits (e.g. «۲-۱»).
TG_EVENT_PICK = "{home}-{away}"

# -- Tick endpoint ---------------------------------------------------------- #
# The scheduler authenticates with this header (compared to TASK_TRIGGER_KEY).
TELEGRAM_TASK_KEY_HEADER = "X-Task-Key"
MSG_TASK_FORBIDDEN = "کلید اجرای زمان‌بندی‌شده نامعتبر است."

# -- Profile API (link status) errors --------------------------------------- #
ERR_TELEGRAM_NOT_CONFIGURED = "اتصال تلگرام در این سرور پیکربندی نشده است."

# -- Model labels (NotificationLog, TelegramState) -------------------------- #
V_NOTIFICATION_LOG = "یادآوری ارسال‌شده"
V_NOTIFICATION_LOG_PLURAL = "یادآوری‌های ارسال‌شده"
L_NOTIFY_KIND = "نوع"
L_NOTIFY_DEDUP_KEY = "کلید یکتا"
L_NOTIFY_SENT_AT = "زمان ارسال"
V_TELEGRAM_STATE = "وضعیت دریافت تلگرام"
V_TELEGRAM_STATE_PLURAL = "وضعیت دریافت تلگرام"
L_TELEGRAM_UPDATE_OFFSET = "آفست به‌روزرسانی‌ها"
L_TELEGRAM_POLLED_AT = "آخرین دریافت به‌روزرسانی‌ها"

