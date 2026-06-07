from django.apps import AppConfig

from . import consts


class PredictionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "predictions"
    verbose_name = consts.BRAND_NAME

    def ready(self):
        # Connect signal handlers (score recomputation on result entry).
        from . import signals  # noqa: F401
