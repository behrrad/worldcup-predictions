import secrets

from django.db import migrations, models

import predictions.models
from predictions import consts


def populate_export_keys(apps, schema_editor):
    """Backfill a unique export key onto every existing league.

    A callable default can't be applied per-row by the schema editor, so we add
    the column unconstrained, fill it here, then enforce uniqueness — that keeps
    leagues created before this field (production has some) from colliding."""
    League = apps.get_model("predictions", "League")
    seen = set()
    for league in League.objects.all():
        key = secrets.token_urlsafe(consts.EXPORT_KEY_BYTES)
        while key in seen:
            key = secrets.token_urlsafe(consts.EXPORT_KEY_BYTES)
        seen.add(key)
        league.export_key = key
        league.save(update_fields=["export_key"])


class Migration(migrations.Migration):

    dependencies = [
        ("predictions", "0003_match_away_label_match_home_label_match_venue"),
    ]

    operations = [
        # 1) Add the column without the unique constraint so existing rows may
        #    briefly share the empty default.
        migrations.AddField(
            model_name="league",
            name="export_key",
            field=models.CharField(
                blank=True,
                default="",
                max_length=consts.EXPORT_KEY_MAX_LENGTH,
                verbose_name=consts.L_EXPORT_KEY,
            ),
        ),
        # 2) Give each existing league its own key.
        migrations.RunPython(populate_export_keys, migrations.RunPython.noop),
        # 3) Enforce uniqueness and the per-instance callable default for new rows.
        migrations.AlterField(
            model_name="league",
            name="export_key",
            field=models.CharField(
                default=predictions.models.generate_export_key,
                help_text=consts.HELP_EXPORT_KEY,
                max_length=consts.EXPORT_KEY_MAX_LENGTH,
                unique=True,
                verbose_name=consts.L_EXPORT_KEY,
            ),
        ),
    ]
