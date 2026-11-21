"""Which menu categories a customer sees, and in which order."""

from collections import defaultdict

from restaurants.models import Restaurant

from .models import MenuCategory


def visible_categories(restaurant: Restaurant) -> list[MenuCategory]:
    """The restaurant's categories that a customer can see, in display order.

    A category is visible when it is active and so is every category above it: hiding a
    category hides its subcategories and their items too. The order is depth first, a
    category immediately followed by its subcategories, and each level by ``sort_order`` and
    then name, so a client that ignores ``parent_id`` still shows a sensible flat list.
    """
    active = list(
        MenuCategory.objects.for_restaurant(restaurant).filter(is_active=True)
    )
    children: dict[object, list[MenuCategory]] = defaultdict(list)
    for category in active:
        children[category.parent_id].append(category)

    ordered: list[MenuCategory] = []
    seen: set[object] = set()

    def walk(parent_id: object) -> None:
        level = sorted(children[parent_id], key=lambda c: (c.sort_order, c.name_en))
        for category in level:
            if category.pk in seen:  # a bad loop can never run on
                continue
            seen.add(category.pk)
            ordered.append(category)
            walk(category.pk)

    # A category whose parent is inactive (or missing from the active rows) is never reached
    # from the top, so it stays hidden.
    walk(None)
    return ordered
