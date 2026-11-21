from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.safestring import SafeString

from core.admin_display import thumbnail
from core.forms import MinorUnitsField
from core.money import format_minor

from .forms import MenuItemAdminForm, OptionAdminForm
from .models import MenuCategory, MenuItem, Option, OptionGroup


class MenuItemInlineForm(forms.ModelForm):  # type: ignore[type-arg]
    """The few fields of an item that are edited from its category's page."""

    price_minor = MinorUnitsField(label="Price (AED)", help_text="For example 12.50")

    class Meta:
        model = MenuItem
        fields = ("name_en", "name_ar", "price_minor", "is_available", "sort_order")


class MenuItemInline(admin.TabularInline):  # type: ignore[type-arg]
    """The items of a category on the category's own page, so a menu is built in one place.
    Descriptions, photos, aliases and options are on the item's page (the link)."""

    model = MenuItem
    form = MenuItemInlineForm
    extra = 0
    fields = ("name_en", "name_ar", "price_minor", "is_available", "sort_order")
    show_change_link = True


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "path_display",
        "name_ar",
        "restaurant",
        "sort_order",
        "is_active",
    )
    list_filter = ("restaurant", "is_active")
    search_fields = ("name_en", "name_ar")
    fields = (
        "restaurant",
        "parent",
        "name_en",
        "name_ar",
        "sort_order",
        "is_active",
    )
    inlines: ClassVar[list[type[admin.options.InlineModelAdmin]]] = [  # type: ignore[type-arg]
        MenuItemInline
    ]

    def get_queryset(self, request: HttpRequest) -> QuerySet[MenuCategory]:
        return (
            super().get_queryset(request).select_related("restaurant", "parent__parent")
        )

    def formfield_for_foreignkey(
        self, db_field: Any, request: HttpRequest, **kwargs: Any
    ) -> Any:
        if db_field.name == "parent":
            # Only a top-level category or a subcategory can have subcategories: a menu has
            # three levels at most. The model checks the rest (same restaurant, no loop).
            kwargs["queryset"] = MenuCategory.objects.filter(
                parent__parent__isnull=True
            ).select_related("restaurant", "parent__parent")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description="Category", ordering="name_en")
    def path_display(self, obj: MenuCategory) -> str:
        return obj.path


class OptionGroupInline(admin.TabularInline):  # type: ignore[type-arg]
    model = OptionGroup
    extra = 0
    fields = ("name_en", "name_ar", "min_select", "max_select", "sort_order")
    show_change_link = True  # options are edited on the group's own page


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    form = MenuItemAdminForm
    list_display = (
        "photo",
        "name_en",
        "name_ar",
        "restaurant",
        "category",
        "price",
        "is_available",
        "sort_order",
    )
    list_display_links = ("name_en", "name_ar")
    list_filter = ("restaurant", "category", "is_available")
    search_fields = ("name_en", "name_ar")
    # The restaurant follows the category; it is shown, not chosen.
    readonly_fields = ("restaurant", "photo_preview")
    inlines: ClassVar[list[type[admin.options.InlineModelAdmin]]] = [  # type: ignore[type-arg]
        OptionGroupInline
    ]

    @admin.display(description="Price (AED)", ordering="price_minor")
    def price(self, obj: MenuItem) -> str:
        return format_minor(obj.price_minor)

    @admin.display(description="Photo")
    def photo(self, obj: MenuItem) -> SafeString:
        return thumbnail(obj.image)

    @admin.display(description="Photo preview")
    def photo_preview(self, obj: MenuItem) -> SafeString:
        return thumbnail(obj.image, large=True)

    def get_fields(self, request: HttpRequest, obj: Any = None) -> list[Any]:
        """The preview sits right under the photo field, not at the end of the form."""
        fields = [f for f in super().get_fields(request, obj) if f != "photo_preview"]
        at = fields.index("image") + 1 if "image" in fields else len(fields)
        fields.insert(at, "photo_preview")
        return fields


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
