from typing import Any

from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest
from django.utils.safestring import SafeString

from core.admin_display import BadgeKind, badge
from core.money import format_minor

from .models import Order, OrderEvent, OrderItem, OrderStatus


class ReadOnlyInline(admin.TabularInline):  # type: ignore[type-arg]
    """Nothing in an order can be added, edited or removed from the admin."""

    extra = 0
    can_delete = False

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class OrderItemInline(ReadOnlyInline):
    model = OrderItem
    ordering = ("line",)
    fields = (
        "line",
        "name_en",
        "name_ar",
        "options",
        "note",
        "quantity",
        "unit_price_minor",
        "line_total_minor",
    )
    readonly_fields = fields


class OrderEventInline(ReadOnlyInline):
    model = OrderEvent
    ordering = ("created_at",)
    fields = ("created_at", "from_status", "to_status", "actor_type", "actor_id")
    readonly_fields = fields


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Read-only: orders are created and moved by the order service, which keeps the history
    and the amounts right. The platform team looks at them here and cannot add or change
    one. A test order can be deleted (with its items and history) on local and staging, but
    never in production, where an order is a real record.

    The customer's coordinates are left out on purpose: a position is shown only to that
    restaurant's staff and the customer. The admin shows the distances and the source.
    """

    list_display = (
        "number",
        "restaurant",
        "customer",
        "status_label",
        "total",
        "distance_m",
        "placed_at",
    )
    list_display_links = ("number",)
    list_filter = ("status", "restaurant")
    search_fields = (
        "vehicle_plate",
        "restaurant__slug",
        "customer__display_name",
        "customer__user__email",
        "customer__user__phone",
    )
    ordering = ("-placed_at",)
    fields = (
        "restaurant",
        "number",
        "customer",
        "conversation",
        "status",
        "fulfilment_type",
        "subtotal_minor",
        "total_minor",
        "currency",
        "customer_note",
        "parking_note",
        "vehicle_plate",
        "vehicle_model",
        "vehicle_colour",
        "location_source",
        "location_accuracy_m",
        "location_captured_at",
        "distance_m",
        "eta_minutes",
        "rejection_reason_code",
        "rejection_note",
        "payment_method",
        "placed_at",
        "accepted_at",
        "rejected_at",
        "ready_at",
        "delivered_at",
        "not_found_at",
        "no_show_at",
        "cancelled_at",
        "created_at",
        "updated_at",
    )
    readonly_fields = fields
    inlines = (OrderItemInline, OrderEventInline)

    @admin.display(description="Total (AED)", ordering="total_minor")
    def total(self, obj: Order) -> str:
        return format_minor(obj.total_minor)

    @admin.display(description="Status", ordering="status")
    def status_label(self, obj: Order) -> SafeString:
        kinds: dict[str, BadgeKind] = {
            OrderStatus.PLACED: "warn",  # waiting for the restaurant
            OrderStatus.ACCEPTED: "info",
            OrderStatus.READY: "ok",
            OrderStatus.DELIVERED: "ok",
            OrderStatus.REJECTED: "bad",
            OrderStatus.NOT_FOUND: "bad",
            OrderStatus.NO_SHOW: "bad",
            OrderStatus.CANCELLED: "muted",
        }
        return badge(obj.get_status_display(), kinds.get(obj.status, "muted"))

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        # Test orders on local and staging can be cleaned up; in production an order is a
        # real record and is never deleted from the admin.
        return settings.ENVIRONMENT != "production" and super().has_delete_permission(
            request, obj
        )
