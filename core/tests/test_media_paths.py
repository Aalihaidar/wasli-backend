"""Where uploaded images are stored: one folder per restaurant, laid out like the admin."""

import pytest
from django.core.files.base import ContentFile
from django.db.models.fields.files import FieldFile

from core.media_paths import extension, kebab
from menu.tests.factories import make_category, make_item
from restaurants.models import RestaurantMenuImage
from restaurants.tests.factories import make_restaurant

pytestmark = pytest.mark.django_db


def _file(name: str) -> ContentFile[bytes]:
    return ContentFile(b"image", name=name)


def _stored(field: FieldFile) -> str:
    return field.name or ""


class TestKebab:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Gulf Food", "gulf-food"),
            ("Chicken_Burger  (Spicy)!", "chicken-burger-spicy"),
            ("  Karak -- Tea ", "karak-tea"),
            ("Cafe 24", "cafe-24"),
        ],
    )
    def test_names_become_lowercase_kebab_case(self, text: str, expected: str) -> None:
        assert kebab(text, "x") == expected

    def test_a_name_with_nothing_usable_gets_the_fallback(self) -> None:
        assert kebab("شاي", "item") == "item"
        assert kebab("", "item") == "item"
        assert kebab(None, "item") == "item"

    def test_a_long_name_is_cut_without_a_trailing_hyphen(self) -> None:
        result = kebab("a" * 39 + " bbbb", "x", limit=40)

        assert len(result) <= 40
        assert not result.endswith("-")

    def test_the_extension_is_lowercase_and_may_be_missing(self) -> None:
        assert extension("Photo.WEBP") == ".webp"
        assert extension("photo") == ""
        assert extension("photo.toolongext") == ""


class TestRestaurantImages:
    def test_the_logo_and_the_cover_have_their_own_folders(self) -> None:
        restaurant = make_restaurant("gulf-food", name_en="Gulf Food")

        restaurant.logo.save("My Logo.PNG", _file("x"))
        restaurant.cover.save("front.jpg", _file("x"))

        assert restaurant.logo.name == "restaurants/gulf-food/logo/logo.png"
        assert restaurant.cover.name == "restaurants/gulf-food/cover/cover.jpg"

    def test_the_folder_is_the_slug_not_the_name(self) -> None:
        restaurant = make_restaurant("cafe-one", name_en="Café One!")

        restaurant.logo.save("a.png", _file("x"))

        assert _stored(restaurant.logo).startswith("restaurants/cafe-one/logo/")

    def test_a_second_upload_never_overwrites_the_first(self) -> None:
        restaurant = make_restaurant("gulf-food")
        restaurant.logo.save("a.png", _file("x"))
        first = restaurant.logo.name

        restaurant.logo.save("b.png", _file("y"))

        assert first == "restaurants/gulf-food/logo/logo.png"
        assert _stored(restaurant.logo) != first
        assert _stored(restaurant.logo).startswith("restaurants/gulf-food/logo/logo_")
        assert _stored(restaurant.logo).endswith(".png")

    def test_a_menu_image_is_named_after_its_caption(self) -> None:
        restaurant = make_restaurant("gulf-food")
        captioned = RestaurantMenuImage(restaurant=restaurant, caption_en="Drinks Menu")
        plain = RestaurantMenuImage(restaurant=restaurant)

        captioned.image.save("scan 1.JPG", _file("x"), save=False)
        plain.image.save("scan 2.jpg", _file("x"), save=False)

        assert (
            captioned.image.name == "restaurants/gulf-food/menu-images/drinks-menu.jpg"
        )
        assert plain.image.name == "restaurants/gulf-food/menu-images/menu-image.jpg"


class TestMenuImages:
    def test_a_category_picture_sits_one_level_above_its_folder(self) -> None:
        restaurant = make_restaurant("gulf-food")
        burgers = make_category(restaurant, "Burgers")
        spicy = make_category(restaurant, "Spicy", parent=burgers)
        extreme = make_category(restaurant, "Extreme Heat", parent=spicy)

        burgers.image.save("p.webp", _file("x"))
        spicy.image.save("p.jpg", _file("x"))
        extreme.image.save("p.WEBP", _file("x"))

        assert burgers.image.name == "restaurants/gulf-food/menu/burgers.webp"
        assert spicy.image.name == "restaurants/gulf-food/menu/burgers/spicy.jpg"
        assert (
            extreme.image.name
            == "restaurants/gulf-food/menu/burgers/spicy/extreme-heat.webp"
        )

    def test_an_item_picture_sits_in_the_folder_of_its_category(self) -> None:
        restaurant = make_restaurant("gulf-food")
        burgers = make_category(restaurant, "Burgers")
        spicy = make_category(restaurant, "Spicy", parent=burgers)
        extreme = make_category(restaurant, "Extreme Heat", parent=spicy)
        top = make_item(burgers, "Chicken Burger")
        deep = make_item(extreme, "Fire Wings (6 pcs)")

        top.image.save("a.jpg", _file("x"))
        deep.image.save("b.webp", _file("x"))

        assert top.image.name == "restaurants/gulf-food/menu/burgers/chicken-burger.jpg"
        assert (
            deep.image.name
            == "restaurants/gulf-food/menu/burgers/spicy/extreme-heat/fire-wings-6-pcs.webp"
        )

    def test_an_item_with_no_english_letters_gets_a_fallback_name(self) -> None:
        restaurant = make_restaurant("gulf-food")
        drinks = make_category(restaurant, "Drinks")
        item = make_item(drinks, "شاي")

        item.image.save("a.jpg", _file("x"))

        assert item.image.name == "restaurants/gulf-food/menu/drinks/item.jpg"

    def test_the_deepest_path_still_fits_the_column(self) -> None:
        restaurant = make_restaurant("a" * 60)
        long_name = "word " * 20
        top = make_category(restaurant, long_name)
        sub = make_category(restaurant, long_name, parent=top)
        subsub = make_category(restaurant, long_name, parent=sub)
        item = make_item(subsub, long_name)

        item.image.save("a.webp", _file("x"))

        assert len(_stored(item.image)) <= 300
