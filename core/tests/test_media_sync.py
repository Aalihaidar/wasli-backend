"""Renaming something in the admin moves its files, so the folders always match the admin."""

import logging
from collections.abc import Callable
from typing import Any

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from menu.models import MenuCategory, MenuItem
from menu.tests.factories import make_category, make_item
from restaurants.models import Restaurant, RestaurantMenuImage
from restaurants.tests.factories import make_restaurant

pytestmark = pytest.mark.django_db

Commit = Callable[..., Any]


def _upload(field: Any, name: str, body: bytes = b"image") -> str:
    field.save(name, ContentFile(body))
    return str(field.name)


def _menu(restaurant: Restaurant) -> dict[str, Any]:
    """Burgers > Spicy, with a picture for each and one item in each."""
    burgers = make_category(restaurant, "Burgers")
    spicy = make_category(restaurant, "Spicy", parent=burgers)
    top = make_item(burgers, "Chicken Burger")
    hot = make_item(spicy, "Hot Wings")
    for row, file_name in (
        (burgers, "b.webp"),
        (spicy, "s.webp"),
        (top, "t.jpg"),
        (hot, "h.jpg"),
    ):
        _upload(row.image, file_name, file_name.encode())
    return {"burgers": burgers, "spicy": spicy, "top": top, "hot": hot}


def _exists(name: str) -> bool:
    return default_storage.exists(name)


class TestRenames:
    def test_renaming_a_category_moves_its_picture_and_everything_inside(
        self, django_capture_on_commit_callbacks: Commit
    ) -> None:
        rows = _menu(make_restaurant("gulf-food"))
        burgers = rows["burgers"]

        with django_capture_on_commit_callbacks(execute=True):
            burgers.name_en = "Grill"
            burgers.save()

        names = {
            key: type(row).objects.get(pk=row.pk).image.name
            for key, row in rows.items()
        }
        assert names == {
            "burgers": "restaurants/gulf-food/menu/grill.webp",
            "spicy": "restaurants/gulf-food/menu/grill/spicy.webp",
            "top": "restaurants/gulf-food/menu/grill/chicken-burger.jpg",
            "hot": "restaurants/gulf-food/menu/grill/spicy/hot-wings.jpg",
        }
        assert all(_exists(name) for name in names.values())
        assert not _exists("restaurants/gulf-food/menu/burgers.webp")
        assert not _exists("restaurants/gulf-food/menu/burgers/chicken-burger.jpg")
        with default_storage.open(names["hot"], "rb") as stored:
            assert stored.read() == b"h.jpg"

    def test_moving_a_category_under_another_moves_its_subtree(
        self, django_capture_on_commit_callbacks: Commit
    ) -> None:
        restaurant = make_restaurant("gulf-food")
        rows = _menu(restaurant)
        drinks = make_category(restaurant, "Drinks")

        with django_capture_on_commit_callbacks(execute=True):
            spicy = MenuCategory.objects.get(pk=rows["spicy"].pk)
            spicy.parent = drinks
            spicy.save()

        assert MenuCategory.objects.get(pk=spicy.pk).image.name == (
            "restaurants/gulf-food/menu/drinks/spicy.webp"
        )
        assert MenuItem.objects.get(pk=rows["hot"].pk).image.name == (
            "restaurants/gulf-food/menu/drinks/spicy/hot-wings.jpg"
        )

    def test_renaming_an_item_renames_its_photo(
        self, django_capture_on_commit_callbacks: Commit
    ) -> None:
        rows = _menu(make_restaurant("gulf-food"))

        with django_capture_on_commit_callbacks(execute=True):
            top = MenuItem.objects.get(pk=rows["top"].pk)
            top.name_en = "Crispy Chicken"
            top.save()

        assert MenuItem.objects.get(pk=top.pk).image.name == (
            "restaurants/gulf-food/menu/burgers/crispy-chicken.jpg"
        )

    def test_changing_the_slug_moves_every_file_of_the_restaurant(
        self, django_capture_on_commit_callbacks: Commit
    ) -> None:
        restaurant = make_restaurant("gulf-food")
        rows = _menu(restaurant)
        _upload(restaurant.logo, "logo.png")
        shot = RestaurantMenuImage(restaurant=restaurant, caption_en="Menu")
        _upload(shot.image, "m.jpg")
        shot.save()

        with django_capture_on_commit_callbacks(execute=True):
            restaurant = Restaurant.objects.get(pk=restaurant.pk)
            restaurant.slug = "gulf-food-dubai"
            restaurant.save()

        assert Restaurant.objects.get(pk=restaurant.pk).logo.name == (
            "restaurants/gulf-food-dubai/logo/logo.png"
        )
        assert RestaurantMenuImage.objects.get(pk=shot.pk).image.name == (
            "restaurants/gulf-food-dubai/menu-images/menu.jpg"
        )
        assert MenuItem.objects.get(pk=rows["hot"].pk).image.name == (
            "restaurants/gulf-food-dubai/menu/burgers/spicy/hot-wings.jpg"
        )
        assert not _exists("restaurants/gulf-food/logo/logo.png")

    def test_a_new_caption_renames_the_menu_image(
        self, django_capture_on_commit_callbacks: Commit
    ) -> None:
        restaurant = make_restaurant("gulf-food")
        shot = RestaurantMenuImage(restaurant=restaurant, caption_en="Menu")
        _upload(shot.image, "m.jpg")
        shot.save()

        with django_capture_on_commit_callbacks(execute=True):
            shot.caption_en = "Drinks Page"
            shot.save()

        assert RestaurantMenuImage.objects.get(pk=shot.pk).image.name == (
            "restaurants/gulf-food/menu-images/drinks-page.jpg"
        )

    def test_another_restaurants_files_are_never_touched(
        self, django_capture_on_commit_callbacks: Commit
    ) -> None:
        rows = _menu(make_restaurant("gulf-food"))
        other = make_restaurant("cafe-two")
        legacy = default_storage.save("menu/items/old.jpg", ContentFile(b"old"))
        stray = make_item(make_category(other, "Tea"), "Karak")
        MenuItem.objects.filter(pk=stray.pk).update(image=legacy)

        with django_capture_on_commit_callbacks(execute=True):
            burgers = rows["burgers"]
            burgers.name_en = "Grill"
            burgers.save()

        assert MenuItem.objects.get(pk=stray.pk).image.name == legacy
        assert _exists(legacy)


class TestWhenItRuns:
    @pytest.fixture
    def calls(self, monkeypatch: pytest.MonkeyPatch) -> list[Any]:
        seen: list[Any] = []

        def organize(restaurant_id: Any = None) -> list[tuple[str, str]]:
            seen.append(restaurant_id)
            return []

        monkeypatch.setattr("core.media_sync.organize", organize)
        return seen

    def test_nothing_runs_before_the_change_is_committed(
        self, calls: list[Any]
    ) -> None:
        restaurant = make_restaurant("gulf-food")

        restaurant.name_en = "Gulf Food Dubai"
        restaurant.save()

        assert calls == []  # the test's transaction never commits

    def test_a_save_of_other_fields_does_not_look_at_the_storage(
        self, calls: list[Any], django_capture_on_commit_callbacks: Commit
    ) -> None:
        restaurant = make_restaurant("gulf-food")

        with django_capture_on_commit_callbacks(execute=True):
            restaurant.next_order_number = 5
            restaurant.save(update_fields=["next_order_number", "updated_at"])

        assert calls == []

    def test_creating_a_row_does_not_look_at_the_storage(
        self, calls: list[Any], django_capture_on_commit_callbacks: Commit
    ) -> None:
        with django_capture_on_commit_callbacks(execute=True):
            restaurant = make_restaurant("gulf-food")
            make_item(make_category(restaurant, "Drinks"), "Tea")

        assert calls == []

    def test_a_rename_looks_only_at_that_restaurant(
        self, calls: list[Any], django_capture_on_commit_callbacks: Commit
    ) -> None:
        restaurant = make_restaurant("gulf-food")
        category = make_category(restaurant, "Drinks")

        with django_capture_on_commit_callbacks(execute=True):
            category.name_en = "Hot Drinks"
            category.save()

        assert calls == [restaurant.pk]

    def test_a_storage_failure_never_fails_the_save(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        django_capture_on_commit_callbacks: Commit,
    ) -> None:
        rows = _menu(make_restaurant("gulf-food"))
        before = MenuItem.objects.get(pk=rows["top"].pk).image.name

        def broken(*args: Any, **kwargs: Any) -> str:
            raise OSError("the storage is down")

        monkeypatch.setattr(default_storage, "save", broken)
        with (
            caplog.at_level(logging.ERROR, logger="core.media"),
            django_capture_on_commit_callbacks(execute=True),
        ):
            burgers = rows["burgers"]
            burgers.name_en = "Grill"
            burgers.save()

        assert MenuCategory.objects.get(pk=burgers.pk).name_en == "Grill"
        assert MenuItem.objects.get(pk=rows["top"].pk).image.name == before
        assert "Could not move the images" in caplog.text
