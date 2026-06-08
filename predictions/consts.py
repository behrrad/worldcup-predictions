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
L_LOCK_MINUTES = "بستن پیش‌بینی (دقیقه قبل از شروع)"
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
HELP_LOCK_MINUTES = "پیش‌بینی هر بازی این تعداد دقیقه پیش از شروع بسته می‌شود."
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
MSG_ADMIN_RECOMPUTED = "{n} امتیاز دوباره محاسبه شد."
COL_SCORE = "نتیجه"
COL_MEMBER_COUNT = "تعداد اعضا"
COL_PREDICTION = "پیش‌بینی"


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

