from menu.models import MenuItem
from menu.services import visible_categories
from restaurants.models import Restaurant

from .types import PromptGroup, PromptItem, PromptMenu, PromptOption


def build_prompt_menu(restaurant: Restaurant) -> PromptMenu:
    """This restaurant's menu as the assistant sees it: every item of a visible category (active, and so are its parents), with
    its aliases, option groups and options, and no price.

    Only this restaurant's rows are read (``for_restaurant``), so another restaurant's items can
    never reach its prompt. Unavailable items are included and flagged: the server, not the
    assistant, tells the customer that one cannot be ordered.
    """
    items = (
        MenuItem.objects.for_restaurant(restaurant)
        .filter(category__in=visible_categories(restaurant))
        .prefetch_related("option_groups__options")
    )
    return PromptMenu(
        items=tuple(
            PromptItem(
                id=str(item.pk),
                name_en=item.name_en,
                name_ar=item.name_ar,
                aliases=tuple(item.aliases),
                is_available=item.is_available,
                option_groups=tuple(
                    PromptGroup(
                        id=str(group.pk),
                        name_en=group.name_en,
                        name_ar=group.name_ar,
                        min_select=group.min_select,
                        max_select=group.max_select,
                        options=tuple(
                            PromptOption(
                                id=str(option.pk),
                                name_en=option.name_en,
                                name_ar=option.name_ar,
                                is_default=option.is_default,
                                is_available=option.is_available,
                            )
                            for option in group.options.all()
                        ),
                    )
                    for group in item.option_groups.all()
                ),
            )
            for item in items
        )
    )
