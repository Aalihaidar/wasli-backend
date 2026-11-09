"""Small helpers that build valid menu rows for tests (invented data only)."""

from menu.models import MenuCategory, MenuItem, Option, OptionGroup
from restaurants.models import Restaurant


def make_category(restaurant: Restaurant, name: str = "Drinks") -> MenuCategory:
    return MenuCategory.objects.create(
        restaurant=restaurant, name_en=name, name_ar="مشروبات"
    )


def make_item(
    category: MenuCategory,
    name: str = "Karak tea",
    price_minor: int = 500,
    **extra: object,
) -> MenuItem:
    return MenuItem.objects.create(
        category=category,
        name_en=name,
        name_ar="شاي",
        price_minor=price_minor,
        **extra,
    )


def make_group(
    item: MenuItem,
    name: str = "Size",
    min_select: int = 0,
    max_select: int = 1,
) -> OptionGroup:
    return OptionGroup.objects.create(
        item=item,
        name_en=name,
        name_ar="الحجم",
        min_select=min_select,
        max_select=max_select,
    )


def make_option(
    group: OptionGroup,
    name: str = "Large",
    price_delta_minor: int = 200,
    **extra: object,
) -> Option:
    return Option.objects.create(
        group=group,
        name_en=name,
        name_ar="كبير",
        price_delta_minor=price_delta_minor,
        **extra,
    )
