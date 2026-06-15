"""Constant strings and labels for the accounts app (kept out of the code)."""

# Field labels
LABEL_EMAIL = "ایمیل"
LABEL_PASSWORD = "گذرواژه"
LABEL_PASSWORD_CONFIRM = "تکرار گذرواژه"
LABEL_DISPLAY_NAME = "نام نمایشی"
LABEL_DISPLAY_NAME_HELP = "نامی که در جدول امتیازات نمایش داده می‌شود."
LABEL_CLERK_ID = "شناسهٔ Clerk"

# Placeholders
PLACEHOLDER_EMAIL = "you@example.com"
PLACEHOLDER_DISPLAY_NAME = "مثلاً: علی"

# Profile field labels
LABEL_AVATAR = "عکس پروفایل"
LABEL_BIO = "دربارهٔ من"
LABEL_LOCATION = "موقعیت مکانی"
LABEL_SOCIAL = "نشانی شبکهٔ اجتماعی"
LABEL_FAVORITE_TEAM = "تیم محبوب"

LABEL_BIO_HELP = "چند جمله دربارهٔ خودت (حداکثر ۲۸۰ نویسه)."
LABEL_LOCATION_HELP = "مثلاً: تهران، ایران"
LABEL_SOCIAL_HELP = "نشانی اینستاگرام، تلگرام یا هر شبکهٔ اجتماعی دیگر."

# Profile field limits
AVATAR_UPLOAD_DIR = "avatars/"
BIO_MAX_LENGTH = 280
LOCATION_MAX_LENGTH = 80
SOCIAL_MAX_LENGTH = 80
AVATAR_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
AVATAR_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
AVATAR_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
AVATAR_DEFAULT_EXTENSION = ".jpg"

# Telegram link (one-tap reminders bot — see predictions/telegram.py)
LABEL_TELEGRAM_CHAT_ID = "شناسهٔ گفتگوی تلگرام"
LABEL_TELEGRAM_NOTIFY = "یادآوری تلگرام فعال"
LABEL_TELEGRAM_LINK_TOKEN = "توکن اتصال تلگرام"
LABEL_TELEGRAM_LINK_TOKEN_AT = "زمان صدور توکن اتصال"
# Max length for a stored Telegram @username (Telegram caps usernames at 32).
TELEGRAM_USERNAME_MAX_LENGTH = 32
TELEGRAM_LINK_TOKEN_MAX_LENGTH = 64

# Verbose names
VERBOSE_USER = "کاربر"
VERBOSE_USER_PLURAL = "کاربران"

# Admin fieldset titles
ADMIN_SECTION_PERSONAL = "اطلاعات شخصی"
ADMIN_SECTION_PROFILE = "پروفایل عمومی"
ADMIN_SECTION_PERMISSIONS = "دسترسی‌ها"
ADMIN_SECTION_DATES = "تاریخ‌ها"

# Messages
MSG_WELCOME = "خوش آمدید! حساب شما ساخته شد."
MSG_PROFILE_UPDATED = "پروفایل به‌روزرسانی شد."

# Profile API validation errors
ERR_AVATAR_REQUIRED = "هیچ فایلی ارسال نشده است."
ERR_AVATAR_TOO_LARGE = "حجم تصویر بیش از حد مجاز است (حداکثر ۵ مگابایت)."
ERR_AVATAR_BAD_TYPE = "فقط فایل تصویری (JPEG، PNG، WebP یا GIF) مجاز است."
ERR_BIO_TOO_LONG = "متن «دربارهٔ من» بیش از حد طولانی است."
ERR_FAVORITE_TEAM_INVALID = "تیم انتخاب‌شده نامعتبر است."

# Validation errors (raised by the user manager)
ERR_EMAIL_REQUIRED = "آدرس ایمیل لازم است."
ERR_SUPERUSER_STAFF = "کاربر ارشد باید is_staff=True داشته باشد."
ERR_SUPERUSER_SUPERUSER = "کاربر ارشد باید is_superuser=True داشته باشد."

# Reusable CSS class for form inputs
INPUT_CSS_CLASS = "input"
