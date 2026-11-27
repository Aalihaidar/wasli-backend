"""Which categories a customer sees, and in which order."""

import pytest

from menu.models import MenuCategory
from menu.services import visible_categories
from menu.tests.factories import make_category
from restaurants.tests.factories import make_restaurant

pytestmark = pytest.mark.django_db


def names(restaurant: object) -> list[str]:
    return [c.name_en for c in visible_categories(restaurant)]  # type: ignore[arg-type]


def test_categories_come_depth_first_each_level_by_sort_order() -> None:
    restaurant = make_restaurant("cafe-a")
    drinks = make_category(restaurant, "Drinks", sort_order=2)
    burgers = make_category(restaurant, "Burgers", sort_order=1)
    make_category(restaurant, "Hot", parent=drinks, sort_order=0)
    crispy = make_category(restaurant, "Crispy", parent=burgers, sort_order=2)
    make_category(restaurant, "Grilled", parent=burgers, sort_order=1)
    make_category(restaurant, "Chicken", parent=crispy, sort_order=0)

    assert names(restaurant) == [
        "Burgers",
        "Grilled",
        "Crispy",
        "Chicken",
        "Drinks",
        "Hot",
    ]


def test_an_inactive_category_hides_its_subcategories_too() -> None:
    restaurant = make_restaurant("cafe-a")
    burgers = make_category(restaurant, "Burgers", is_active=False)
    grilled = make_category(restaurant, "Grilled", parent=burgers)
    make_category(restaurant, "Chicken", parent=grilled)
    make_category(restaurant, "Drinks")

    assert names(restaurant) == ["Drinks"]


def test_an_inactive_subcategory_hides_only_its_own_branch() -> None:
    restaurant = make_restaurant("cafe-a")
    burgers = make_category(restaurant, "Burgers")
    grilled = make_category(restaurant, "Grilled", parent=burgers, is_active=False)
    make_category(restaurant, "Chicken", parent=grilled)
    make_category(restaurant, "Crispy", parent=burgers)

    assert names(restaurant) == ["Burgers", "Crispy"]


def test_only_this_restaurants_categories_are_listed() -> None:
    a, b = make_restaurant("cafe-a"), make_restaurant("cafe-b")
    make_category(a, "Burgers")
    make_category(b, "Other")

    assert names(a) == ["Burgers"]
    assert MenuCategory.objects.count() == 2


def test_a_menu_without_categories_is_empty() -> None:
    assert names(make_restaurant("cafe-a")) == []
