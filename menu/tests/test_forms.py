import pytest
from django import forms

from menu.forms import AliasesField, MenuItemAdminForm, OptionAdminForm
from menu.tests.factories import make_category, make_group, make_item, make_option
from restaurants.tests.factories import make_restaurant

pytestmark = pytest.mark.django_db


class TestAliasesField:
    def test_lines_and_commas_become_a_clean_list(self) -> None:
        assert AliasesField().clean("karak\n chai ,Karak\n\n") == ["karak", "chai"]

    def test_empty_text_is_an_empty_list(self) -> None:
        assert AliasesField().clean("") == []

    def test_a_list_is_shown_one_per_line(self) -> None:
        assert AliasesField().prepare_value(["karak", "chai"]) == "karak\nchai"

    def test_a_too_long_alias_is_refused(self) -> None:
        with pytest.raises(forms.ValidationError):
            AliasesField().clean("x" * 61)

    def test_unchanged_aliases_are_not_a_change(self) -> None:
        field = AliasesField()

        assert field.has_changed(["karak", "chai"], "karak\nchai") is False
        assert field.has_changed(["karak"], "karak\nchai") is True


class TestMenuItemForm:
    def test_it_saves_aed_as_minor_units_and_aliases_as_a_list(self) -> None:
        category = make_category(make_restaurant("cafe-a"))
        form = MenuItemAdminForm(
            {
                "category": str(category.pk),
                "name_en": "Karak tea",
                "name_ar": "شاي كرك",
                "price_minor": "12.50",
                "aliases": "karak\nchai",
                "is_available": "on",
                "sort_order": "0",
            }
        )

        assert form.is_valid(), form.errors
        item = form.save()
        assert item.price_minor == 1250
        assert item.aliases == ["karak", "chai"]
        assert item.restaurant_id == category.restaurant_id

    def test_a_price_with_three_decimals_is_refused(self) -> None:
        category = make_category(make_restaurant("cafe-a"))
        form = MenuItemAdminForm(
            {
                "category": str(category.pk),
                "name_en": "Tea",
                "name_ar": "شاي",
                "price_minor": "12.555",
                "sort_order": "0",
            }
        )

        assert not form.is_valid()
        assert "price_minor" in form.errors

    def test_an_existing_item_shows_its_price_in_aed(self) -> None:
        item = make_item(
            make_category(make_restaurant("cafe-a")),
            price_minor=1250,
            aliases=["karak"],
        )

        form = MenuItemAdminForm(instance=item)

        assert form["price_minor"].value() == "12.50"
        assert form["aliases"].value() == "karak"


class TestOptionForm:
    def test_a_negative_price_change_is_saved_in_minor_units(self) -> None:
        group = make_group(make_item(make_category(make_restaurant("cafe-a"))))
        form = OptionAdminForm(
            {
                "group": str(group.pk),
                "name_en": "Small",
                "name_ar": "صغير",
                "price_delta_minor": "-1.00",
                "is_available": "on",
                "sort_order": "0",
            }
        )

        assert form.is_valid(), form.errors
        assert form.save().price_delta_minor == -100

    def test_an_existing_option_shows_its_change_in_aed(self) -> None:
        group = make_group(make_item(make_category(make_restaurant("cafe-a"))))
        option = make_option(group, price_delta_minor=200)

        assert OptionAdminForm(instance=option)["price_delta_minor"].value() == "2.00"
