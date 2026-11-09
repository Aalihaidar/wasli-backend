from collections.abc import Sequence
from typing import Any, ClassVar

from django.contrib import admin
from django.http import HttpRequest

from .models import ParkingLot, Restaurant, RestaurantMenuImage, StaffMembership


@admin.register(ParkingLot)
class ParkingLotAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("name", "address", "radius_m", "latitude", "longitude")
    search_fields = ("name", "address")


class RestaurantMenuImageInline(admin.TabularInline):  # type: ignore[type-arg]
    model = RestaurantMenuImage
    extra = 0
    fields = ("image", "caption_en", "caption_ar", "sort_order")


class StaffMembershipInline(admin.TabularInline):  # type: ignore[type-arg]
    model = StaffMembership
    extra = 0
    can_delete = False  # members are deactivated, never deleted
    fields = ("user", "role", "is_active")
    raw_id_fields = ("user",)


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "name_en",
        "slug",
        "parking_lot",
        "is_active",
        "is_demo",
        "subscription_status",
        "subscription_paid_until",
    )
    list_filter = ("is_active", "is_demo", "subscription_status", "parking_lot")
    search_fields = ("name_en", "name_ar", "slug", "phone")
    prepopulated_fields: ClassVar[dict[str, Sequence[str]]] = {"slug": ("name_en",)}
    readonly_fields = (
        "screen_last_seen_at",
        "next_order_number",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (None, {"fields": ("slug", "name_en", "name_ar", "is_active", "is_demo")}),
        (
            "Place",
            {"fields": ("parking_lot", "address", "latitude", "longitude", "phone")},
        ),
        ("Look", {"fields": ("logo", "cover", "brand_colour")}),
        (
            "Chat",
            {
                "fields": (
                    "welcome_message_en",
                    "welcome_message_ar",
                    "default_eta_minutes",
                )
            },
        ),
        (
            "Subscription and payment",
            {
                "fields": (
                    "subscription_status",
                    "subscription_paid_until",
                    "accepts_cash",
                    "accepts_card",
                )
            },
        ),
        ("Settings", {"fields": ("timezone",)}),
        (
            "System",
            {
                "fields": (
                    "screen_last_seen_at",
                    "next_order_number",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )
    inlines: ClassVar[list[type[admin.options.InlineModelAdmin]]] = [  # type: ignore[type-arg]
        StaffMembershipInline,
        RestaurantMenuImageInline,
    ]

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False  # restaurants are deactivated, never deleted


@admin.register(StaffMembership)
class StaffMembershipAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("user", "restaurant", "role", "is_active")
    list_filter = ("role", "is_active", "restaurant")
    search_fields = ("user__username", "user__full_name", "restaurant__name_en")
    raw_id_fields = ("user",)
    actions = (
        None  # the bulk delete bypasses the last-admin rule; members are deactivated
    )
