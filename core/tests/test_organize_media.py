"""organize_media: move the stored images to the folder layout without breaking a row."""

import io

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.db import models

from chat.models import MessageKind, Sender
from chat.services import add_message
from chat.tests.factories import make_conversation
from menu.models import MenuCategory, MenuItem
from menu.tests.factories import make_category, make_item
from restaurants.models import Restaurant, RestaurantMenuImage
from restaurants.tests.factories import make_restaurant

pytestmark = pytest.mark.django_db


def _store(name: str, body: bytes = b"image") -> str:
    return default_storage.save(name, ContentFile(body))


def _run(*args: str) -> str:
    out = io.StringIO()
    call_command("organize_media", *args, stdout=out)
    return out.getvalue()


def _name(model: type[models.Model], pk: object, field: str = "image") -> str:
    return str(getattr(model._default_manager.get(pk=pk), field).name)


class TestOrganizeMedia:
    def test_a_dry_run_lists_the_moves_and_changes_nothing(self) -> None:
        restaurant = make_restaurant("gulf-food")
        old = _store("restaurants/logos/old.png")
        Restaurant.objects.filter(pk=restaurant.pk).update(logo=old)

        output = _run("--dry-run")

        assert f"{old}  ->  restaurants/gulf-food/logo/logo.png" in output
        assert "1 image(s) would move." in output
        assert _name(Restaurant, restaurant.pk, "logo") == old
        assert default_storage.exists(old)
        assert not default_storage.exists("restaurants/gulf-food/logo/logo.png")

    def test_every_kind_of_image_moves_and_keeps_its_content(self) -> None:
        restaurant = make_restaurant("gulf-food")
        burgers = make_category(restaurant, "Burgers")
        item = make_item(burgers, "Chicken Burger")
        shot = RestaurantMenuImage.objects.create(
            restaurant=restaurant, image="x", caption_en="Drinks Menu"
        )
        Restaurant.objects.filter(pk=restaurant.pk).update(
            logo=_store("restaurants/logos/a.png", b"logo"),
            cover=_store("restaurants/covers/b.jpg", b"cover"),
        )
        MenuItem.objects.filter(pk=item.pk).update(
            image=_store("menu/items/c.jpg", b"item")
        )
        RestaurantMenuImage.objects.filter(pk=shot.pk).update(
            image=_store("restaurants/menu/d.jpg", b"shot")
        )

        output = _run()

        assert "4 image(s) moved." in output
        expected = {
            (Restaurant, restaurant.pk, "logo"): (
                "restaurants/gulf-food/logo/logo.png",
                b"logo",
            ),
            (Restaurant, restaurant.pk, "cover"): (
                "restaurants/gulf-food/cover/cover.jpg",
                b"cover",
            ),
            (MenuItem, item.pk, "image"): (
                "restaurants/gulf-food/menu/burgers/chicken-burger.jpg",
                b"item",
            ),
            (RestaurantMenuImage, shot.pk, "image"): (
                "restaurants/gulf-food/menu-images/drinks-menu.jpg",
                b"shot",
            ),
        }
        for (model, pk, field), (name, body) in expected.items():
            assert _name(model, pk, field) == name
            with default_storage.open(name, "rb") as stored:
                assert stored.read() == body
        for old in (
            "restaurants/logos/a.png",
            "restaurants/covers/b.jpg",
            "menu/items/c.jpg",
            "restaurants/menu/d.jpg",
        ):
            assert not default_storage.exists(old)

    def test_the_welcome_messages_follow_the_menu_image(self) -> None:
        conversation = make_conversation()
        shot = RestaurantMenuImage.objects.create(
            restaurant=conversation.restaurant, image="x", caption_en="Menu"
        )
        old = _store("restaurants/menu/old.jpg")
        RestaurantMenuImage.objects.filter(pk=shot.pk).update(image=old)
        message = add_message(
            conversation, Sender.BOT, MessageKind.IMAGE, image=old, text="Menu"
        )

        _run()

        message.refresh_from_db()
        moved = _name(RestaurantMenuImage, shot.pk)
        assert moved.endswith("/menu-images/menu.jpg")
        assert message.image.name == moved

    def test_a_second_run_finds_nothing_to_move(self) -> None:
        restaurant = make_restaurant("gulf-food")
        Restaurant.objects.filter(pk=restaurant.pk).update(
            logo=_store("restaurants/logos/a.png")
        )
        _run()

        output = _run()

        assert "0 image(s) moved." in output

    def test_a_file_with_the_random_suffix_counts_as_in_place(self) -> None:
        restaurant = make_restaurant("gulf-food")
        name = _store("restaurants/gulf-food/logo/logo_k3j9d2.png")
        Restaurant.objects.filter(pk=restaurant.pk).update(logo=name)

        output = _run()

        assert "0 image(s) moved." in output
        assert _name(Restaurant, restaurant.pk, "logo") == name

    def test_a_missing_file_is_reported_and_its_row_is_left_alone(self) -> None:
        restaurant = make_restaurant("gulf-food")
        Restaurant.objects.filter(pk=restaurant.pk).update(
            logo="restaurants/logos/gone.png"
        )

        output = _run()

        assert "MISSING  restaurants/logos/gone.png" in output
        assert "1 row(s) name a file that is not in the storage" in output
        assert _name(Restaurant, restaurant.pk, "logo") == "restaurants/logos/gone.png"

    def test_a_file_two_rows_share_stays_until_both_have_moved(self) -> None:
        restaurant = make_restaurant("gulf-food")
        drinks = make_category(restaurant, "Drinks")
        tea = make_item(drinks, "Tea")
        coffee = make_item(drinks, "Coffee")
        shared = _store("menu/items/shared.jpg", b"both")
        MenuItem.objects.filter(pk__in=[tea.pk, coffee.pk]).update(image=shared)

        _run()

        assert _name(MenuItem, tea.pk) == "restaurants/gulf-food/menu/drinks/tea.jpg"
        assert (
            _name(MenuItem, coffee.pk) == "restaurants/gulf-food/menu/drinks/coffee.jpg"
        )
        assert not default_storage.exists(shared)

    def test_a_renamed_category_regroups_its_items(self) -> None:
        restaurant = make_restaurant("gulf-food")
        burgers = make_category(restaurant, "Burgers")
        item = make_item(burgers, "Chicken Burger")
        item.image.save("a.jpg", ContentFile(b"x"))
        before = item.image.name
        MenuCategory.objects.filter(pk=burgers.pk).update(name_en="Grill")

        _run()

        after = _name(MenuItem, item.pk)
        assert before == "restaurants/gulf-food/menu/burgers/chicken-burger.jpg"
        assert after == "restaurants/gulf-food/menu/grill/chicken-burger.jpg"
        assert not default_storage.exists(before)
