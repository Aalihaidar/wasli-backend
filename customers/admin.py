from typing import Any

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone

from .models import Customer, CustomerBlock, CustomerSession, Vehicle


class VehicleInline(admin.TabularInline):  # type: ignore[type-arg]
    model = Vehicle
    extra = 0
    fields = ("plate", "colour", "make_model", "last_used_at")
    readonly_fields = ("last_used_at",)


class CustomerSessionInline(admin.TabularInline):  # type: ignore[type-arg]
    model = CustomerSession
    extra = 0
    can_delete = False
    fields = ("user_agent", "created_at", "last_seen_at", "revoked_at")
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False  # a session is started by signing in, never by hand


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "__str__",
        "user",
        "locale",
        "is_blocked",
        "last_seen_at",
        "created_at",
    )
    list_filter = ("is_blocked", "locale")
    search_fields = (
        "display_name",
        "user__email",
        "user__phone",
        "user__username",
    )
    raw_id_fields = ("user",)
    readonly_fields = ("last_seen_at", "created_at", "updated_at")
    inlines = (VehicleInline, CustomerSessionInline)


@admin.register(CustomerSession)
class CustomerSessionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Read-only: the platform team can see and revoke sessions, not create or edit them."""

    list_display = (
        "customer",
        "user_agent",
        "last_seen_at",
        "revoked_at",
        "created_at",
    )
    list_filter = ("revoked_at",)
    search_fields = ("customer__display_name", "customer__user__email")
    actions = ("revoke_selected",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    @admin.action(description="Revoke the selected sessions")
    def revoke_selected(
        self, request: HttpRequest, queryset: QuerySet[CustomerSession]
    ) -> None:
        now = timezone.now()
        revoked = queryset.filter(revoked_at__isnull=True).update(
            revoked_at=now, updated_at=now
        )
        self.message_user(request, f"{revoked} session(s) revoked.")


@admin.register(CustomerBlock)
class CustomerBlockAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("customer", "restaurant", "reason", "created_at")
    list_filter = ("restaurant",)
    raw_id_fields = ("customer",)
