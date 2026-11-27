from typing import Any
from uuid import uuid4

import pytest

from menu.models import MenuItem
from menu.tests.factories import (
    make_category,
    make_group,
    make_item,
    make_option,
)
from orders.errors import OrderError, ProblemCode
from orders.models import MAX_LINES, MAX_QUANTITY
from orders.pricing import price_lines
from restaurants.models import Restaurant
from restaurants.tests.factories import make_restaurant

pytestmark = pytest.mark.django_db


def line(item: MenuItem, quantity: int = 1, **extra: Any) -> dict[str, Any]:
    return {
        "item_id": str(item.pk),
        "quantity": quantity,
        "option_ids": [],
        "note": "",
        **extra,
    }


def problems_of(restaurant: Restaurant, lines: list[dict[str, Any]]) -> OrderError:
    with pytest.raises(OrderError) as raised:
        price_lines(restaurant, lines)
    return raised.value


class TestTotals:
    def test_quantity_times_price(self) -> None:
        restaurant = make_restaurant()
        item = make_item(make_category(restaurant), price_minor=300)

        order = price_lines(restaurant, [line(item, 2)])

        assert order.lines[0].unit_price_minor == 300
        assert order.lines[0].line_total_minor == 600
        assert order.subtotal_minor == order.total_minor == 600
        assert order.currency == "AED"

    def test_options_change_the_unit_price_and_may_be_negative(self) -> None:
        restaurant = make_restaurant()
        item = make_item(make_category(restaurant), price_minor=300)
        group = make_group(item, max_select=2)
        large = make_option(group, "Large", 200)
        no_sugar = make_option(group, "No sugar", -50)

        order = price_lines(
            restaurant,
            [line(item, 3, option_ids=[str(large.pk), str(no_sugar.pk)])],
        )

        assert order.lines[0].unit_price_minor == 450
        assert order.lines[0].line_total_minor == 1350
        assert [o.name_en for o in order.lines[0].options] == ["Large", "No sugar"]
        assert order.lines[0].option_ids == [large.pk, no_sugar.pk]

    def test_several_lines_add_up_and_are_numbered_from_one(self) -> None:
        restaurant = make_restaurant()
        category = make_category(restaurant)
        tea = make_item(category, "Karak tea", 300)
        sandwich = make_item(category, "Cheese sandwich", 1200)

        order = price_lines(
            restaurant, [line(tea, 2, note=" less sugar "), line(sandwich)]
        )

        assert [entry.line for entry in order.lines] == [1, 2]
        assert order.lines[0].note == "less sugar"
        assert order.subtotal_minor == 1800

    def test_the_same_item_may_be_on_two_lines(self) -> None:
        restaurant = make_restaurant()
        item = make_item(make_category(restaurant), price_minor=300)
        group = make_group(item)
        large = make_option(group, "Large", 200)

        order = price_lines(
            restaurant, [line(item), line(item, option_ids=[str(large.pk)])]
        )

        assert [entry.unit_price_minor for entry in order.lines] == [300, 500]

    def test_an_english_only_entry_gets_its_english_name_in_arabic_too(self) -> None:
        restaurant = make_restaurant()
        category = make_category(restaurant)
        item = MenuItem.objects.create(
            category=category, name_en="Angus Burger", price_minor=2100
        )

        order = price_lines(restaurant, [line(item)])

        assert order.lines[0].name_ar == "Angus Burger"

    def test_a_duplicated_option_counts_once(self) -> None:
        restaurant = make_restaurant()
        item = make_item(make_category(restaurant), price_minor=300)
        large = make_option(make_group(item), "Large", 200)

        order = price_lines(
            restaurant, [line(item, option_ids=[str(large.pk), str(large.pk)])]
        )

        assert order.lines[0].unit_price_minor == 500

    def test_the_number_of_queries_does_not_grow_with_the_lines(
        self, django_assert_max_num_queries: Any
    ) -> None:
        restaurant = make_restaurant()
        category = make_category(restaurant)
        items = [make_item(category, f"Item {n}", 100 + n) for n in range(6)]
        for item in items:
            make_option(make_group(item), "Large", 100)

        with django_assert_max_num_queries(6):
            price_lines(restaurant, [line(item) for item in items])


class TestItems:
    def test_an_empty_order_is_refused(self) -> None:
        assert problems_of(make_restaurant(), []).codes == {ProblemCode.EMPTY_ORDER}

    def test_too_many_lines_are_refused(self) -> None:
        restaurant = make_restaurant()
        item = make_item(make_category(restaurant))

        error = problems_of(restaurant, [line(item)] * (MAX_LINES + 1))

        assert error.codes == {ProblemCode.TOO_MANY_LINES}

    def test_an_unknown_or_malformed_item_id_is_reported_with_its_line(self) -> None:
        restaurant = make_restaurant()
        item = make_item(make_category(restaurant))

        error = problems_of(
            restaurant,
            [line(item), {"item_id": str(uuid4()), "quantity": 1}, {"item_id": "x"}],
        )

        assert [(p.code, p.line) for p in error.problems] == [
            (ProblemCode.UNKNOWN_ITEM, 2),
            (ProblemCode.UNKNOWN_ITEM, 3),
        ]

    def test_another_restaurants_item_is_unknown(self) -> None:
        restaurant = make_restaurant("cafe-one")
        other = make_restaurant("cafe-two")
        foreign = make_item(make_category(other))

        error = problems_of(restaurant, [line(foreign)])

        assert error.codes == {ProblemCode.UNKNOWN_ITEM}

    def test_an_item_that_is_finished_is_unavailable(self) -> None:
        restaurant = make_restaurant()
        item = make_item(make_category(restaurant), is_available=False)

        error = problems_of(restaurant, [line(item)])

        assert error.problems[0].code == ProblemCode.ITEM_UNAVAILABLE
        assert error.problems[0].item_id == item.pk

    def test_an_item_in_a_hidden_category_is_unavailable(self) -> None:
        restaurant = make_restaurant()
        parent = make_category(restaurant, "Burgers", is_active=False)
        child = make_category(restaurant, "Grilled", parent=parent)
        item = make_item(child)

        assert problems_of(restaurant, [line(item)]).codes == {
            ProblemCode.ITEM_UNAVAILABLE
        }

    @pytest.mark.parametrize(
        "quantity", [0, -1, MAX_QUANTITY + 1, True, "2", 1.5, None]
    )
    def test_a_quantity_outside_one_to_twenty_is_refused(self, quantity: Any) -> None:
        restaurant = make_restaurant()
        item = make_item(make_category(restaurant))

        error = problems_of(restaurant, [line(item, quantity)])

        assert error.codes == {ProblemCode.INVALID_QUANTITY}

    def test_the_largest_quantity_is_accepted(self) -> None:
        restaurant = make_restaurant()
        item = make_item(make_category(restaurant), price_minor=100)

        order = price_lines(restaurant, [line(item, MAX_QUANTITY)])

        assert order.total_minor == 100 * MAX_QUANTITY

    def test_a_long_note_is_refused(self) -> None:
        restaurant = make_restaurant()
        item = make_item(make_category(restaurant))

        error = problems_of(restaurant, [line(item, note="x" * 201)])

        assert error.codes == {ProblemCode.NOTE_TOO_LONG}

    def test_every_problem_of_every_line_is_listed_at_once(self) -> None:
        restaurant = make_restaurant()
        category = make_category(restaurant)
        finished = make_item(category, "Finished", is_available=False)
        fine = make_item(category, "Fine")

        error = problems_of(
            restaurant, [line(finished), line(fine, 99), {"item_id": "nope"}]
        )

        assert [p.code for p in error.problems] == [
            ProblemCode.ITEM_UNAVAILABLE,
            ProblemCode.INVALID_QUANTITY,
            ProblemCode.UNKNOWN_ITEM,
        ]

    @pytest.mark.parametrize(
        "change",
        [{"is_active": False}, {"subscription_status": "suspended"}],
    )
    def test_a_restaurant_that_is_not_public_takes_no_order(
        self, change: dict[str, Any]
    ) -> None:
        restaurant = make_restaurant(**change)
        item = make_item(make_category(restaurant))

        error = problems_of(restaurant, [line(item)])

        assert error.codes == {ProblemCode.RESTAURANT_UNAVAILABLE}


class TestOptions:
    def test_an_option_of_another_item_is_unknown(self) -> None:
        restaurant = make_restaurant()
        category = make_category(restaurant)
        tea = make_item(category, "Karak tea")
        coffee = make_item(category, "Coffee")
        other = make_option(make_group(coffee), "Large")

        error = problems_of(restaurant, [line(tea, option_ids=[str(other.pk)])])

        assert error.problems[0].code == ProblemCode.UNKNOWN_OPTION
        assert error.problems[0].option_id == other.pk

    def test_an_option_that_is_not_a_uuid_is_unknown(self) -> None:
        restaurant = make_restaurant()
        item = make_item(make_category(restaurant))

        error = problems_of(restaurant, [line(item, option_ids=["large"])])

        assert error.codes == {ProblemCode.UNKNOWN_OPTION}

    def test_an_option_that_is_finished_is_unavailable(self) -> None:
        restaurant = make_restaurant()
        item = make_item(make_category(restaurant))
        group = make_group(item)
        gone = make_option(group, "Large", is_available=False)

        error = problems_of(restaurant, [line(item, option_ids=[str(gone.pk)])])

        assert error.problems[0].code == ProblemCode.OPTION_UNAVAILABLE
        assert error.problems[0].group_id == group.pk

    def test_a_required_group_the_customer_skipped_gets_its_default(self) -> None:
        restaurant = make_restaurant()
        item = make_item(make_category(restaurant), price_minor=300)
        group = make_group(item, "Size", min_select=1, max_select=1)
        make_option(group, "Small", 0, is_default=True)
        make_option(group, "Large", 200)

        order = price_lines(restaurant, [line(item)])

        assert [o.name_en for o in order.lines[0].options] == ["Small"]
        assert order.lines[0].unit_price_minor == 300

    def test_a_default_is_not_added_to_an_optional_group(self) -> None:
        restaurant = make_restaurant()
        item = make_item(make_category(restaurant))
        group = make_group(item, min_select=0)
        make_option(group, "Small", 0, is_default=True)

        assert price_lines(restaurant, [line(item)]).lines[0].options == ()

    def test_the_customers_choice_wins_over_the_default(self) -> None:
        restaurant = make_restaurant()
        item = make_item(make_category(restaurant), price_minor=300)
        group = make_group(item, min_select=1)
        make_option(group, "Small", 0, is_default=True)
        large = make_option(group, "Large", 200)

        order = price_lines(restaurant, [line(item, option_ids=[str(large.pk)])])

        assert [o.name_en for o in order.lines[0].options] == ["Large"]

    def test_a_required_group_with_no_default_needs_an_answer(self) -> None:
        restaurant = make_restaurant()
        item = make_item(make_category(restaurant))
        group = make_group(item, min_select=1)
        make_option(group, "Small")

        error = problems_of(restaurant, [line(item)])

        assert error.problems[0].code == ProblemCode.OPTION_RULE
        assert error.problems[0].group_id == group.pk
        assert error.problems[0].line == 1

    def test_too_many_choices_in_a_group_are_refused(self) -> None:
        restaurant = make_restaurant()
        item = make_item(make_category(restaurant))
        group = make_group(item, max_select=1)
        small = make_option(group, "Small")
        large = make_option(group, "Large")

        error = problems_of(
            restaurant, [line(item, option_ids=[str(small.pk), str(large.pk)])]
        )

        assert error.codes == {ProblemCode.OPTION_RULE}

    def test_a_required_group_whose_only_choice_is_finished_is_not_silently_replaced(
        self,
    ) -> None:
        restaurant = make_restaurant()
        item = make_item(make_category(restaurant))
        group = make_group(item, min_select=1)
        make_option(group, "Small", is_default=True)
        gone = make_option(group, "Large", is_available=False)

        error = problems_of(restaurant, [line(item, option_ids=[str(gone.pk)])])

        assert error.codes == {ProblemCode.OPTION_UNAVAILABLE}

    def test_a_price_that_would_be_negative_is_refused(self) -> None:
        restaurant = make_restaurant()
        item = make_item(make_category(restaurant), price_minor=100)
        discount = make_option(make_group(item), "Voucher", -500)

        error = problems_of(restaurant, [line(item, option_ids=[str(discount.pk)])])

        assert error.codes == {ProblemCode.INVALID_PRICE}
