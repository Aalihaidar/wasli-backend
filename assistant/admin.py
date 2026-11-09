from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from .models import AICallLog


@admin.register(AICallLog)
class AICallLogAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Read-only, and nothing can be deleted: the daily budget guard counts these rows, so
    removing one would give the day's quota back by mistake."""

    list_display = (
        "created_at",
        "provider",
        "model",
        "purpose",
        "input_kind",
        "outcome",
        "latency_ms",
        "restaurant",
    )
    list_filter = ("outcome", "purpose", "provider", "input_kind")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
