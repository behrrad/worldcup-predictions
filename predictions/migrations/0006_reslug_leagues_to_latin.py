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

from predictions import consts
from predictions.models import fa_to_latin_slug


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
        base = fa_to_latin_slug(league.name) or consts.SLUG_FALLBACK_LEAGUE
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
