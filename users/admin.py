from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import (
    AdminUserCreationForm,
)
from django.contrib.auth.forms import (
    UserChangeForm as DjangoUserChangeForm,
)

from .models import User

# Django's UsernameField cannot handle a blank value, and here a blank username is stored
# as NULL, so a plain CharField is used instead.
_FIELD_CLASSES: dict[str, type[forms.Field]] = {"username": forms.CharField}


class UserCreationForm(AdminUserCreationForm):  # type: ignore[type-arg]
    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("username", "email", "phone", "full_name", "must_change_password")
        field_classes = _FIELD_CLASSES


class UserChangeForm(DjangoUserChangeForm):  # type: ignore[type-arg]
    class Meta(DjangoUserChangeForm.Meta):
        model = User
        field_classes = _FIELD_CLASSES


@admin.register(User)
class UserAdmin(DjangoUserAdmin):  # type: ignore[type-arg]
    form = UserChangeForm
    add_form = UserCreationForm
    ordering = ("username", "email", "phone")
    list_display = (
        "__str__",
        "username",
        "email",
        "phone",
        "full_name",
        "is_active",
        "is_staff",
        "is_superuser",
    )
    list_filter = ("is_active", "is_staff", "is_superuser", "must_change_password")
    search_fields = ("username", "email", "phone", "full_name")
    readonly_fields = ("last_login", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("username", "email", "phone", "password")}),
        ("Personal info", {"fields": ("full_name",)}),
        (
            "Verification and password",
            {
                "fields": (
                    "email_verified_at",
                    "phone_verified_at",
                    "must_change_password",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "phone",
                    "full_name",
                    "must_change_password",
                    "usable_password",
                    "password1",
                    "password2",
                ),
            },
        ),
    )
