from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from .models import Conversation, Message


class MessageInline(admin.TabularInline):  # type: ignore[type-arg]
    """The messages of a conversation, in order. Messages are append-only, so nothing here
    can be added, edited or removed."""

    model = Message
    extra = 0
    can_delete = False
    ordering = ("seq",)
    fields = ("seq", "sender", "kind", "text", "transcript", "used_voice", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Read-only: the platform team can look at a conversation and clear test ones, not
    create or change them (the engine owns their state).

    The customer's coordinates are left out on purpose: a position is shown only to that
    restaurant's staff and the customer. The admin shows only where it came from.
    """

    list_display = (
        "restaurant",
        "customer",
        "state",
        "locale",
        "last_seq",
        "last_activity_at",
        "expires_at",
        "closed_at",
    )
    list_filter = ("state", "locale", "restaurant")
    search_fields = (
        "restaurant__slug",
        "customer__display_name",
        "customer__user__email",
        "customer__user__phone",
    )
    ordering = ("-last_activity_at",)
    fields = (
        "restaurant",
        "customer",
        "state",
        "locale",
        "lines",
        "pending_question",
        "pending_field",
        "return_to_review",
        "parking_note",
        "vehicle_plate",
        "vehicle_model",
        "vehicle_colour",
        "order_note",
        "location_source",
        "location_captured_at",
        "last_seq",
        "last_activity_at",
        "expires_at",
        "closed_at",
        "created_at",
        "updated_at",
    )
    readonly_fields = fields
    inlines = (MessageInline,)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
