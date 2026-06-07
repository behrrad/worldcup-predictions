from django.apps import AppConfig

from . import consts


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = consts.VERBOSE_USER_PLURAL
