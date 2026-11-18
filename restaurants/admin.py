from collections.abc import Sequence
from typing import Any, ClassVar

from django.contrib import admin
from django.http import HttpRequest
from django.utils.safestring import SafeString

from core.admin_display import BadgeKind, badge, thumbnail

from .models import ParkingLot, Restaurant, RestaurantMenuImage, StaffMembership
from .services import screen_is_online


@admin.register(ParkingLot)
class ParkingLotAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("name", "address", "radius_m", "latitude", "longitude")
    search_fields = ("name", "address")


class RestaurantMenuImageInline(admin.TabularInline):  # type: ignore[type-arg]
    model = RestaurantMenuImage
    extra = 0
    fields = ("image", "preview", "caption_en", "caption_ar", "sort_order")
    readonly_fields = ("preview",)

    @admin.display(description="Preview")
    def preview(self, obj: RestaurantMenuImage) -> SafeString:
        return thumbnail(obj.image)


class StaffMembershipInline(admin.TabularInline):  # type: ignore[type-arg]
    model = StaffMembership
    extra = 0
    can_delete = False  # members are deactivated, never deleted
    fields = ("user", "role", "is_active")
    raw_id_fields = ("user",)


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "logo_thumb",
        "name_en",
        "slug",
        "parking_lot",
        "is_active",
        "site_online",
        "subscription",
        "is_demo",
        "subscription_paid_until",
    )
    list_display_links = ("name_en", "slug")
    list_filter = ("is_active", "is_demo", "subscription_status", "parking_lot")
    search_fields = ("name_en", "name_ar", "slug", "phone")
    prepopulated_fields: ClassVar[dict[str, Sequence[str]]] = {"slug": ("name_en",)}
    readonly_fields = (
        "logo_preview",
        "cover_preview",
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
        (
            "Look",
            {
                "fields": (
                    "logo",
                    "logo_preview",
                    "cover",
                    "cover_preview",
                    "brand_colour",
                )
            },
        ),
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

    @admin.display(description="Logo")
    def logo_thumb(self, obj: Restaurant) -> SafeString:
        return thumbnail(obj.logo)

    @admin.display(description="Logo")
    def logo_preview(self, obj: Restaurant) -> SafeString:
        return thumbnail(obj.logo, large=True)

    @admin.display(description="Cover")
    def cover_preview(self, obj: Restaurant) -> SafeString:
        return thumbnail(obj.cover, large=True)

    @admin.display(description="Site online", boolean=True)
    def site_online(self, obj: Restaurant) -> bool:
        """The restaurant's site polled in the last minute, so it can take an order."""
        return screen_is_online(obj)

    @admin.display(description="Subscription", ordering="subscription_status")
    def subscription(self, obj: Restaurant) -> SafeString:
        kinds: dict[str, BadgeKind] = {
            "trial": "info",
            "active": "ok",
            "suspended": "bad",
        }
        return badge(
            obj.get_subscription_status_display(),
            kinds.get(obj.subscription_status, "muted"),
        )

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
