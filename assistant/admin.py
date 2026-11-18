from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from django.utils.safestring import SafeString

from core.admin_display import BadgeKind, badge

from .models import AICallLog, Outcome


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
        "outcome_label",
        "latency_ms",
        "restaurant",
    )
    list_filter = ("outcome", "purpose", "provider", "input_kind")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    @admin.display(description="Outcome", ordering="outcome")
    def outcome_label(self, obj: AICallLog) -> SafeString:
        kinds: dict[str, BadgeKind] = {
            Outcome.OK: "ok",
            Outcome.TIMEOUT: "warn",
            Outcome.RATE_LIMITED: "warn",
            Outcome.BUDGET_EXCEEDED: "warn",
            Outcome.INVALID_OUTPUT: "bad",
            Outcome.ERROR: "bad",
        }
        return badge(obj.get_outcome_display(), kinds.get(obj.outcome, "muted"))

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
