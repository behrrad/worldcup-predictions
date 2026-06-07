from django.contrib.auth.models import AbstractUser
from django.db import models

from . import consts
from .managers import UserManager


class User(AbstractUser):
    """Custom user that logs in with an email address instead of a username."""

    username = None  # remove the username field
    email = models.EmailField(consts.LABEL_EMAIL, unique=True)
    display_name = models.CharField(
        consts.LABEL_DISPLAY_NAME,
        max_length=60,
        blank=True,
        help_text=consts.LABEL_DISPLAY_NAME_HELP,
    )
    clerk_id = models.CharField(
        consts.LABEL_CLERK_ID, max_length=80, unique=True, null=True, blank=True,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # email & password are required by default

    objects = UserManager()

    class Meta:
        verbose_name = consts.VERBOSE_USER
        verbose_name_plural = consts.VERBOSE_USER_PLURAL

    def __str__(self):
        return self.display_name or self.email

    @property
    def public_name(self) -> str:
        """Best name to show publicly on leaderboards."""
        return self.display_name or self.email.split("@")[0]
