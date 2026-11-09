from typing import ClassVar

from django.contrib import admin

from core.money import format_minor

from .forms import MenuItemAdminForm, OptionAdminForm
from .models import MenuCategory, MenuItem, Option, OptionGroup


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("name_en", "name_ar", "restaurant", "sort_order", "is_active")
    list_filter = ("restaurant", "is_active")
    search_fields = ("name_en", "name_ar")


class OptionGroupInline(admin.TabularInline):  # type: ignore[type-arg]
    model = OptionGroup
    extra = 0
    fields = ("name_en", "name_ar", "min_select", "max_select", "sort_order")
    show_change_link = True  # options are edited on the group's own page


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    form = MenuItemAdminForm
    list_display = (
        "name_en",
        "name_ar",
        "restaurant",
        "category",
        "price",
        "is_available",
        "sort_order",
    )
    list_filter = ("restaurant", "category", "is_available")
    search_fields = ("name_en", "name_ar")
    # The restaurant follows the category; it is shown, not chosen.
    readonly_fields = ("restaurant",)
    inlines: ClassVar[list[type[admin.options.InlineModelAdmin]]] = [  # type: ignore[type-arg]
        OptionGroupInline
    ]

    @admin.display(description="Price (AED)", ordering="price_minor")
    def price(self, obj: MenuItem) -> str:
        return format_minor(obj.price_minor)


class OptionInline(admin.TabularInline):  # type: ignore[type-arg]
    model = Option
    form = OptionAdminForm
    extra = 0
    fields = (
        "name_en",
        "name_ar",
        "price_delta_minor",
        "is_available",
        "is_default",
        "sort_order",
    )


@admin.register(OptionGroup)
class OptionGroupAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("name_en", "item", "restaurant", "min_select", "max_select")
    list_filter = ("restaurant",)
    search_fields = ("name_en", "name_ar", "item__name_en")
    readonly_fields = ("restaurant",)
    inlines: ClassVar[list[type[admin.options.InlineModelAdmin]]] = [  # type: ignore[type-arg]
        OptionInline
    ]
