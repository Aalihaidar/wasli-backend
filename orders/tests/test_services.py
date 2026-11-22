from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from chat.models import Conversation, ConversationState
from chat.tests.factories import make_conversation
from customers.errors import PhoneNotVerified
from customers.models import Vehicle
from customers.tests.factories import make_customer
from menu.models import MenuItem
from menu.tests.factories import make_category, make_group, make_item, make_option
from orders.errors import OrderError, ProblemCode
from orders.models import ActorType, Order, OrderEvent, OrderStatus
from orders.services import place_order
from restaurants.models import Restaurant
from restaurants.tests.factories import make_restaurant

pytestmark = pytest.mark.django_db

NEAR: dict[str, Any] = {
    "location_lat": 25.2002,
    "location_lng": 55.2702,
}  # about 15 m from the door
FAR: dict[str, Any] = {
    "location_lat": 25.2501,
    "location_lng": 55.2701,
}  # about 5.5 km away


def ready(
    restaurant: Restaurant | None = None, **extra: Any
) -> tuple[Conversation, MenuItem]:
    """A conversation in the review state with a valid order and a valid car."""
    restaurant = restaurant or make_restaurant("cafe-svc")
    item = make_item(make_category(restaurant), "Karak tea", 300)
    values: dict[str, Any] = {
        "state": ConversationState.REVIEW,
        "lines": [
            {
                "line": 1,
                "item_id": str(item.pk),
                "quantity": 2,
                "option_ids": [],
                "note": "less sugar",
            }
        ],
        "parking_note": "Parking B2 near the lift",
        "vehicle_plate": "a  12345",
        "vehicle_model": "Toyota Camry",
        "vehicle_colour": "White",
        "order_note": "No straw please",
        **extra,
    }
    return make_conversation(restaurant, **values), item


def next_number(restaurant: Restaurant) -> int:
    restaurant.refresh_from_db()
    return restaurant.next_order_number


class TestPlaceOrder:
    def test_it_creates_the_order_with_copies_of_everything(self) -> None:
        conversation, item = ready(
            **NEAR,
            location_accuracy_m=15,
            location_source="gps",
            location_captured_at=timezone.now(),
        )

        order = place_order(conversation)

        assert order.number == 1
        assert order.status == OrderStatus.PLACED
        assert order.order_type == "car"
        assert order.restaurant == conversation.restaurant
        assert order.customer == conversation.customer
        assert order.conversation == conversation
        assert (order.subtotal_minor, order.total_minor) == (600, 600)
        assert order.customer_note == "No straw please"
        assert order.parking_note == "Parking B2 near the lift"
        assert order.vehicle_plate == "A 12345"
        assert order.vehicle_model == "Toyota Camry"
        assert order.vehicle_colour == "White"
        assert order.location_source == "gps"
        assert order.location_accuracy_m == 15
        assert order.distance_m is not None
        assert 5 <= order.distance_m <= 40
        assert order.distance_band.value == "in_lot"
        line = order.items.get()
        assert (line.line, line.quantity, line.unit_price_minor) == (1, 2, 300)
        assert line.line_total_minor == 600
        assert line.note == "less sugar"
        assert line.menu_item == item
        assert (line.name_en, line.name_ar) == ("Karak tea", "شاي")

    def test_the_options_are_copied_with_their_names_and_price_changes(self) -> None:
        conversation, item = ready()
        large = make_option(make_group(item), "Large", 200)
        conversation.lines = [
            {"item_id": str(item.pk), "quantity": 1, "option_ids": [str(large.pk)]}
        ]
        conversation.save()

        order = place_order(conversation)

        line = order.items.get()
        assert line.unit_price_minor == 500
        assert line.options == [
            {"name_en": "Large", "name_ar": "كبير", "price_delta_minor": 200}
        ]

    def test_later_menu_changes_never_rewrite_the_order(self) -> None:
        conversation, item = ready()
        order = place_order(conversation)

        item.name_en = "Chai"
        item.price_minor = 999
        item.save()

        line = order.items.get()
        assert (line.name_en, line.unit_price_minor, line.line_total_minor) == (
            "Karak tea",
            300,
            600,
        )

    def test_an_english_only_entry_keeps_its_english_name_for_both_languages(
        self,
    ) -> None:
        restaurant = make_restaurant("gulf-food")
        burger = MenuItem.objects.create(
            category=make_category(restaurant), name_en="Angus Burger", price_minor=2100
        )
        conversation, _ = ready(
            restaurant,
            lines=[{"item_id": str(burger.pk), "quantity": 1, "option_ids": []}],
        )

        line = place_order(conversation).items.get()

        assert (line.name_en, line.name_ar) == ("Angus Burger", "Angus Burger")

    def test_the_conversation_is_placed_and_the_history_has_its_first_event(
        self,
    ) -> None:
        conversation, _ = ready()

        order = place_order(conversation)

        conversation.refresh_from_db()
        assert conversation.state == ConversationState.PLACED
        assert conversation.closed_at is not None
        event = OrderEvent.objects.get(order=order)
        assert (event.from_status, event.to_status) == ("", "placed")
        assert event.actor_type == ActorType.CUSTOMER
        assert event.actor_id == conversation.customer.user_id

    def test_order_numbers_run_on_per_restaurant(self) -> None:
        restaurant = make_restaurant("cafe-numbers")
        other = make_restaurant("cafe-other")
        first, _ = ready(restaurant)
        second, _ = ready(restaurant, customer=make_customer("omar@example.com"))
        elsewhere, _ = ready(other, customer=make_customer("lina@example.com"))

        numbers = [place_order(c).number for c in (first, second, elsewhere)]

        assert numbers == [1, 2, 1]
        assert next_number(restaurant) == 3

    def test_the_car_is_saved_for_next_time_and_updated_when_it_comes_back(
        self,
    ) -> None:
        customer = make_customer()
        restaurant = make_restaurant("cafe-cars")
        first, _ = ready(restaurant, customer=customer)
        place_order(first)
        vehicle = Vehicle.objects.get(customer=customer)
        assert (vehicle.plate, vehicle.make_model, vehicle.colour) == (
            "A 12345",
            "Toyota Camry",
            "White",
        )

        second, _ = ready(restaurant, customer=customer, vehicle_colour="Black")
        place_order(second)

        vehicle = Vehicle.objects.get(customer=customer)
        assert vehicle.colour == "Black"
        assert vehicle.last_used_at is not None

    def test_without_a_position_the_order_is_still_placed(self) -> None:
        conversation, _ = ready()

        order = place_order(conversation)

        assert order.customer_lat is None
        assert order.location_source == "none"
        assert order.distance_m is None
        assert order.distance_band.value == "unknown"


class TestWhatStopsIt:
    def test_a_conversation_that_is_not_in_review_is_refused(self) -> None:
        conversation, _ = ready(state=ConversationState.ORDERING)

        with pytest.raises(OrderError) as raised:
            place_order(conversation)

        assert raised.value.codes == {ProblemCode.WRONG_STATE}
        assert not Order.objects.exists()

    def test_one_conversation_creates_one_order(self) -> None:
        conversation, _ = ready()
        place_order(conversation)

        with pytest.raises(OrderError) as raised:
            place_order(conversation)

        assert raised.value.codes == {ProblemCode.ALREADY_PLACED}
        assert Order.objects.count() == 1

    def test_an_expired_conversation_is_refused(self) -> None:
        conversation, _ = ready(expires_at=timezone.now() - timedelta(minutes=1))

        with pytest.raises(OrderError) as raised:
            place_order(conversation)

        assert raised.value.codes == {ProblemCode.CONVERSATION_EXPIRED}

    def test_only_a_car_order_is_accepted(self) -> None:
        conversation, _ = ready(order_type="delivery")

        with pytest.raises(OrderError) as raised:
            place_order(conversation)

        assert raised.value.codes == {ProblemCode.UNSUPPORTED_ORDER_TYPE}

    def test_an_incomplete_car_is_refused_and_names_what_is_missing(self) -> None:
        conversation, _ = ready(vehicle_plate="", vehicle_colour="W")

        with pytest.raises(OrderError) as raised:
            place_order(conversation)

        problem = raised.value.problems[0]
        assert problem.code == ProblemCode.CAR_DETAILS_INCOMPLETE
        assert problem.fields == ("plate", "colour")
        assert next_number(conversation.restaurant) == 1

    def test_an_item_that_ran_out_since_the_review_is_refused(self) -> None:
        conversation, item = ready()
        item.is_available = False
        item.save()

        with pytest.raises(OrderError) as raised:
            place_order(conversation)

        assert raised.value.codes == {ProblemCode.ITEM_UNAVAILABLE}
        assert not Order.objects.exists()
        assert next_number(conversation.restaurant) == 1
        conversation.refresh_from_db()
        assert conversation.state == ConversationState.REVIEW

    def test_an_empty_order_is_refused(self) -> None:
        conversation, _ = ready(lines=[])

        with pytest.raises(OrderError) as raised:
            place_order(conversation)

        assert raised.value.codes == {ProblemCode.EMPTY_ORDER}

    def test_a_restaurant_that_was_suspended_takes_no_order(self) -> None:
        conversation, _ = ready()
        Restaurant.objects.filter(pk=conversation.restaurant_id).update(
            subscription_status="suspended"
        )

        with pytest.raises(OrderError) as raised:
            place_order(conversation)

        assert raised.value.codes == {ProblemCode.RESTAURANT_UNAVAILABLE}


class TestThePhoneCheck:
    def test_it_does_nothing_while_the_setting_is_off(self, settings: Any) -> None:
        settings.REQUIRE_VERIFIED_PHONE = False
        conversation, _ = ready()

        assert place_order(conversation).number == 1

    def test_an_unverified_phone_is_refused_before_anything_is_written(
        self, settings: Any
    ) -> None:
        settings.REQUIRE_VERIFIED_PHONE = True
        conversation, _ = ready()

        with pytest.raises(PhoneNotVerified):
            place_order(conversation)

        assert not Order.objects.exists()
        assert next_number(conversation.restaurant) == 1
        conversation.refresh_from_db()
        assert conversation.state == ConversationState.REVIEW
        assert conversation.closed_at is None

    def test_the_same_confirmation_works_once_the_phone_is_verified(
        self, settings: Any
    ) -> None:
        settings.REQUIRE_VERIFIED_PHONE = True
        conversation, _ = ready()
        with pytest.raises(PhoneNotVerified):
            place_order(conversation)

        user = conversation.customer.user
        user.phone = "+971501234567"
        user.phone_verified_at = timezone.now()
        user.save()

        assert place_order(conversation).number == 1


class TestTheServiceDistance:
    def restaurant_with_radius(self, radius: int | None = 300) -> Restaurant:
        return make_restaurant("cafe-radius", service_radius_m=radius)

    @pytest.mark.parametrize("mode", ["warn", "off"])
    def test_warn_and_off_record_a_far_order_and_never_refuse_it(
        self, settings: Any, mode: str
    ) -> None:
        settings.LOCATION_CHECK = mode
        conversation, _ = ready(self.restaurant_with_radius(), **FAR)

        order = place_order(conversation)

        assert order.distance_m is not None
        assert order.distance_m > 5000
        assert order.distance_band.value == "far"

    def test_enforce_refuses_an_order_from_outside_the_service_distance(
        self, settings: Any
    ) -> None:
        settings.LOCATION_CHECK = "enforce"
        restaurant = self.restaurant_with_radius()
        conversation, _ = ready(restaurant, **FAR)

        with pytest.raises(OrderError) as raised:
            place_order(conversation)

        assert raised.value.codes == {ProblemCode.OUTSIDE_SERVICE_DISTANCE}
        assert not Order.objects.exists()
        assert next_number(restaurant) == 1

    def test_enforce_accepts_an_order_from_inside_it(self, settings: Any) -> None:
        settings.LOCATION_CHECK = "enforce"
        conversation, _ = ready(self.restaurant_with_radius(), **NEAR)

        assert place_order(conversation).number == 1

    def test_enforce_never_refuses_a_restaurant_with_no_service_distance(
        self, settings: Any
    ) -> None:
        settings.LOCATION_CHECK = "enforce"
        conversation, _ = ready(self.restaurant_with_radius(None), **FAR)

        assert place_order(conversation).number == 1

    def test_enforce_never_refuses_an_order_without_a_position(
        self, settings: Any
    ) -> None:
        settings.LOCATION_CHECK = "enforce"
        conversation, _ = ready(self.restaurant_with_radius())

        assert place_order(conversation).distance_m is None
