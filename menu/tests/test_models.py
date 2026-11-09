import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from menu.models import (
    MAX_ALIASES,
    MenuCategory,
    MenuItem,
    Option,
    OptionGroup,
    clean_aliases,
)
from menu.tests.factories import make_category, make_group, make_item, make_option
from restaurants.tests.factories import make_restaurant

pytestmark = pytest.mark.django_db


class TestCleanAliases:
    def test_it_trims_drops_empties_and_duplicates(self) -> None:
        assert clean_aliases(["  karak ", "Karak", "", "chai   karak", "KARAK"]) == [
            "karak",
            "chai karak",
        ]

    def test_an_empty_list_is_fine(self) -> None:
        assert clean_aliases([]) == []

    @pytest.mark.parametrize("value", ["karak", None, {"a": 1}, 5])
    def test_it_must_be_a_list(self, value: object) -> None:
        with pytest.raises(ValidationError):
            clean_aliases(value)

    def test_every_alias_must_be_text(self) -> None:
        with pytest.raises(ValidationError):
            clean_aliases(["karak", 5])

    def test_an_alias_has_a_length_limit(self) -> None:
        with pytest.raises(ValidationError):
            clean_aliases(["x" * 61])

    def test_the_number_of_aliases_is_limited(self) -> None:
        names = [f"name {n}" for n in range(MAX_ALIASES + 1)]

        with pytest.raises(ValidationError):
            clean_aliases(names)


class TestMenuCategory:
    def test_defaults_and_str(self) -> None:
        category = make_category(make_restaurant("cafe-a"), "Drinks")

        assert category.is_active is True
        assert category.sort_order == 0
        assert str(category) == "Cafe A: Drinks"

    def test_categories_are_ordered_by_sort_order(self) -> None:
        restaurant = make_restaurant("cafe-a")
        late = MenuCategory.objects.create(
            restaurant=restaurant, name_en="A", name_ar="أ", sort_order=2
        )
        early = MenuCategory.objects.create(
            restaurant=restaurant, name_en="B", name_ar="ب", sort_order=1
        )

        assert list(MenuCategory.objects.all()) == [early, late]

    def test_a_category_with_items_cannot_be_deleted(self) -> None:
        category = make_category(make_restaurant("cafe-a"))
        make_item(category)

        with pytest.raises(ProtectedError):
            category.delete()


class TestMenuItem:
    def test_the_restaurant_follows_the_category(self) -> None:
        restaurant = make_restaurant("cafe-a")
        item = MenuItem(
            category=make_category(restaurant),
            name_en="Tea",
            name_ar="شاي",
            price_minor=500,
        )

        item.full_clean(exclude=["restaurant"])
        item.save()

        assert item.restaurant_id == restaurant.pk

    def test_an_item_cannot_name_another_restaurant_than_its_category(self) -> None:
        category = make_category(make_restaurant("cafe-a"))
        other = make_restaurant("cafe-b")
        item = MenuItem(
            restaurant=other,
            category=category,
            name_en="Tea",
            name_ar="شاي",
            price_minor=500,
        )

        with pytest.raises(ValidationError) as error:
            item.full_clean()
        assert "category" in error.value.message_dict
        with pytest.raises(ValidationError):
            item.save()
        assert not MenuItem.objects.exists()

    def test_defaults(self) -> None:
        item = make_item(make_category(make_restaurant("cafe-a")))

        assert item.is_available is True
        assert item.aliases == []
        assert item.price_minor == 500
        assert str(item) == "Karak tea"

    def test_aliases_are_normalised_on_save(self) -> None:
        item = make_item(
            make_category(make_restaurant("cafe-a")),
            aliases=["  karak ", "Karak", "chai"],
        )

        item.refresh_from_db()
        assert item.aliases == ["karak", "chai"]

    def test_bad_aliases_are_rejected(self) -> None:
        category = make_category(make_restaurant("cafe-a"))

        with pytest.raises(ValidationError):
            make_item(category, aliases="karak")

    def test_a_price_cannot_be_negative(self) -> None:
        category = make_category(make_restaurant("cafe-a"))
        item = MenuItem(category=category, name_en="T", name_ar="ت", price_minor=0)
        item.full_clean(exclude=["restaurant"])  # free is allowed

        with pytest.raises(IntegrityError), transaction.atomic():
            make_item(category, price_minor=-1)

    def test_items_of_two_restaurants_stay_apart(self) -> None:
        a, b = make_restaurant("cafe-a"), make_restaurant("cafe-b")
        item_a = make_item(make_category(a))
        make_item(make_category(b))

        assert list(MenuItem.objects.for_restaurant(a)) == [item_a]


class TestOptionGroup:
    def test_the_restaurant_follows_the_item(self) -> None:
        restaurant = make_restaurant("cafe-a")
        group = make_group(make_item(make_category(restaurant)))

        assert group.restaurant_id == restaurant.pk
        assert (group.min_select, group.max_select) == (0, 1)

    def test_a_group_cannot_name_another_restaurant_than_its_item(self) -> None:
        item = make_item(make_category(make_restaurant("cafe-a")))
        group = OptionGroup(
            restaurant=make_restaurant("cafe-b"),
            item=item,
            name_en="Size",
            name_ar="الحجم",
        )

        with pytest.raises(ValidationError):
            group.save()

    def test_the_maximum_cannot_be_below_the_minimum(self) -> None:
        item = make_item(make_category(make_restaurant("cafe-a")))
        group = OptionGroup(
            item=item, name_en="Size", name_ar="الحجم", min_select=2, max_select=1
        )

        with pytest.raises(ValidationError) as error:
            group.full_clean(exclude=["restaurant"])
        assert "max_select" in error.value.message_dict

    def test_the_database_also_refuses_a_maximum_below_the_minimum(self) -> None:
        item = make_item(make_category(make_restaurant("cafe-a")))
        group = make_group(item)

        with pytest.raises(IntegrityError), transaction.atomic():
            OptionGroup.objects.filter(pk=group.pk).update(min_select=3, max_select=1)

    def test_the_maximum_must_be_at_least_one(self) -> None:
        item = make_item(make_category(make_restaurant("cafe-a")))
        group = OptionGroup(
            item=item, name_en="Size", name_ar="الحجم", min_select=0, max_select=0
        )

        with pytest.raises(ValidationError) as error:
            group.full_clean(exclude=["restaurant"])
        assert "max_select" in error.value.message_dict

    def test_deleting_an_item_removes_its_groups_and_options(self) -> None:
        item = make_item(make_category(make_restaurant("cafe-a")))
        make_option(make_group(item))

        item.delete()

        assert not OptionGroup.objects.exists()
        assert not Option.objects.exists()


class TestOption:
    def test_the_restaurant_follows_the_group(self) -> None:
        restaurant = make_restaurant("cafe-a")
        option = make_option(make_group(make_item(make_category(restaurant))))

        assert option.restaurant_id == restaurant.pk
        assert option.is_available is True
        assert option.is_default is False

    def test_an_option_cannot_name_another_restaurant_than_its_group(self) -> None:
        group = make_group(make_item(make_category(make_restaurant("cafe-a"))))
        option = Option(
            restaurant=make_restaurant("cafe-b"),
            group=group,
            name_en="Large",
            name_ar="كبير",
        )

        with pytest.raises(ValidationError):
            option.save()

    def test_a_price_change_can_be_negative(self) -> None:
        group = make_group(make_item(make_category(make_restaurant("cafe-a"))))

        option = make_option(group, "Small", price_delta_minor=-100)

        option.refresh_from_db()
        assert option.price_delta_minor == -100

    def test_an_unavailable_option_cannot_be_the_default(self) -> None:
        group = make_group(make_item(make_category(make_restaurant("cafe-a"))))

        with pytest.raises(ValidationError) as error:
            make_option(group, is_default=True, is_available=False)
        assert "is_default" in error.value.message_dict

    def test_a_single_choice_group_has_one_default_at_most(self) -> None:
        group = make_group(
            make_item(make_category(make_restaurant("cafe-a"))), max_select=1
        )
        make_option(group, "Medium", is_default=True)

        with pytest.raises(ValidationError):
            make_option(group, "Large", is_default=True)
        assert Option.objects.filter(group=group, is_default=True).count() == 1

    def test_a_multiple_choice_group_can_have_several_defaults(self) -> None:
        group = make_group(
            make_item(make_category(make_restaurant("cafe-a"))), max_select=2
        )
        make_option(group, "Sugar", is_default=True)
        make_option(group, "Milk", is_default=True)

        with pytest.raises(ValidationError):
            make_option(group, "Cardamom", is_default=True)

    def test_changing_an_existing_default_does_not_count_it_twice(self) -> None:
        group = make_group(
            make_item(make_category(make_restaurant("cafe-a"))), max_select=1
        )
        option = make_option(group, is_default=True)

        option.name_en = "Medium"
        option.save()

        option.refresh_from_db()
        assert option.name_en == "Medium"

    def test_another_groups_defaults_do_not_count(self) -> None:
        item = make_item(make_category(make_restaurant("cafe-a")))
        make_option(make_group(item, "Size"), is_default=True)

        make_option(make_group(item, "Milk"), is_default=True)

    def test_options_of_two_restaurants_stay_apart(self) -> None:
        a, b = make_restaurant("cafe-a"), make_restaurant("cafe-b")
        option_a = make_option(make_group(make_item(make_category(a))))
        make_option(make_group(make_item(make_category(b))))

        assert list(Option.objects.for_restaurant(a)) == [option_a]
