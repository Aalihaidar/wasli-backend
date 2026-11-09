from typing import Any

from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest

from .models import OutboxMessage


@admin.register(OutboxMessage)
class OutboxMessageAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Where the owner reads the verification codes on local and staging. Nothing is added
    or edited by hand; a message can be deleted to tidy the list, but never in production."""

    list_display = ("created_at", "channel", "recipient", "purpose", "subject")
    list_filter = ("channel", "purpose")
    search_fields = ("recipient",)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = (
        "channel",
        "recipient",
        "subject",
        "body",
        "purpose",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return bool(
            settings.ENVIRONMENT != "production"
        ) and super().has_delete_permission(request, obj)
