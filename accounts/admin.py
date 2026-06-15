from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm

from . import consts
from .forms import AdminUserChangeForm, AdminUserCreationForm
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    add_form = AdminUserCreationForm
    form = AdminUserChangeForm
    change_password_form = AdminPasswordChangeForm
    model = User

    list_display = ("email", "display_name", "is_staff", "is_active", "date_joined")
    list_filter = ("is_staff", "is_superuser", "is_active")
    search_fields = ("email", "display_name", "clerk_id")
    ordering = ("email",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (consts.ADMIN_SECTION_PERSONAL, {"fields": ("display_name", "clerk_id",
                                                    "first_name", "last_name")}),
        (consts.ADMIN_SECTION_PROFILE, {"fields": ("avatar", "bio", "location",
                                                   "social_handle", "favorite_team")}),
        (consts.ADMIN_SECTION_PERMISSIONS, {"fields": ("is_active", "is_staff", "is_superuser",
                                                       "groups", "user_permissions")}),
        (consts.ADMIN_SECTION_DATES, {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "display_name", "password1", "password2"),
        }),
    )


# Re-register the auth Group so it picks up the Unfold theme too (Django
# registers it with its own un-themed admin at import time).
admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass
