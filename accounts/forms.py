# Unfold's form variants are drop-in subclasses of Django's that restyle the
# password/permission widgets to match the themed admin. Keeping our custom
# field sets, we just swap the base classes.
from unfold.forms import UserChangeForm, UserCreationForm

from .models import User


class AdminUserCreationForm(UserCreationForm):
    """Used by the Django admin to create users manually."""

    class Meta:
        model = User
        fields = ("email", "display_name")


class AdminUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = ("email", "display_name", "clerk_id", "is_active", "is_staff",
                  "is_superuser", "groups", "user_permissions")
