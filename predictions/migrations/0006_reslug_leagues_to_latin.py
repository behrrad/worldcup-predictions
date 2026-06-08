# Re-slug existing leagues from Persian to readable ASCII (transliterated).
#
# Until now a league named «لیگ دوستان» got the Persian slug «لیگ-دوستان», which
# percent-encodes into gibberish in URLs (/l/%D9%84%DB%8C%DA%AF-...). Going
# forward League.save() transliterates the name to Latin; this migration brings
# the leagues already in the database in line, so their links become readable too.
#
# Only leagues whose slug contains a non-ASCII character are touched — any league
# already on an ASCII slug (English name, or one customised by hand in the admin)
# is left exactly as it is. Competitions are deliberately untouched: their slugs
# are set explicitly by the seed commands and used as CLI lookup keys.
from django.db import migrations
from django.utils.text import slugify

# A *frozen* copy of the transliteration map + fallback as of this migration.
# Data migrations must be reproducible: importing predictions.consts /
# predictions.models would let a later edit to the live map silently change what
# this one-time backfill produces. Keeping a local copy pins the behavior.
_FA_TO_LATIN = {
    "ا": "a", "آ": "a", "أ": "a", "إ": "a", "ٱ": "a", "ى": "a",
    "ء": "", "ئ": "y", "ؤ": "v",
    "ب": "b", "پ": "p", "ت": "t", "ث": "s", "ج": "j", "چ": "ch",
    "ح": "h", "خ": "kh", "د": "d", "ذ": "z", "ر": "r", "ز": "z",
    "ژ": "zh", "س": "s", "ش": "sh", "ص": "s", "ض": "z", "ط": "t",
    "ظ": "z", "ع": "a", "غ": "gh", "ف": "f", "ق": "gh",
    "ک": "k", "ك": "k", "گ": "g", "ل": "l", "م": "m", "ن": "n",
    "و": "u", "ه": "h", "ة": "h", "ۀ": "e", "ی": "i", "ي": "i",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "‌": "", "‍": "", "ـ": "",
    "ً": "", "ٌ": "", "ٍ": "", "َ": "",
    "ُ": "", "ِ": "", "ّ": "", "ْ": "",
    "ٓ": "", "ٔ": "", "ٕ": "",
}
_SLUG_FALLBACK_LEAGUE = "league"


def _fa_to_latin_slug(text: str) -> str:
    return slugify("".join(_FA_TO_LATIN.get(ch, ch) for ch in text))


def _is_ascii(value: str) -> bool:
    return all(ord(ch) < 128 for ch in value)


def reslug_leagues(apps, schema_editor):
    League = apps.get_model("predictions", "League")

    # Reserve the ASCII slugs we're keeping so a regenerated slug can't collide
    # with them; then assign new slugs in a stable order (oldest first).
    taken = {
        slug
        for slug in League.objects.values_list("slug", flat=True)
        if _is_ascii(slug)
    }

    for league in League.objects.order_by("created_at", "pk"):
        if _is_ascii(league.slug):
            continue
        base = _fa_to_latin_slug(league.name) or _SLUG_FALLBACK_LEAGUE
        slug = base
        n = 2
        while slug in taken:
            slug = f"{base}-{n}"
            n += 1
        taken.add(slug)
        league.slug = slug
        league.save(update_fields=["slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("predictions", "0005_league_reveal_predictions"),
    ]

    # Irreversible: the original Persian slugs can't be reconstructed from the
    # Latin ones, and reverting wouldn't help anyone.
    operations = [
        migrations.RunPython(reslug_leagues, migrations.RunPython.noop),
    ]
