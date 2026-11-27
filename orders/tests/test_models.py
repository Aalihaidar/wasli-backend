import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from chat.tests.factories import make_conversation
from core.geo import DistanceBand
from customers.tests.factories import make_customer
from menu.tests.factories import make_category, make_item
from orders.models import (
    Order,
    OrderEvent,
    OrderItem,
    OrderStatus,
    RejectionReason,
)
from orders.tests.factories import make_event, make_order, make_order_item
from restaurants.tests.factories import make_restaurant

pytestmark = pytest.mark.django_db


class TestOrder:
    def test_defaults(self) -> None:
        before = timezone.now()
        order = make_order()

        assert order.pk.version == 4
        assert order.status == OrderStatus.PLACED
        assert order.order_type == "car"
        assert order.currency == "AED"
        assert order.customer_lat is None
        assert order.location_source == "none"
        assert order.eta_minutes is None
        assert order.rejection_reason_code == ""
        assert order.payment_method == ""
        assert before <= order.placed_at <= timezone.now()
        assert order.accepted_at is None

    def test_the_text_names_the_number_and_restaurant(self) -> None:
        order = make_order(make_restaurant("cafe-a"))

        assert str(order) == "#1 Cafe A"

    def test_it_takes_the_restaurant_and_customer_of_its_conversation(self) -> None:
        conversation = make_conversation()
        order = Order.objects.create(
            conversation=conversation,
            customer=conversation.customer,
            number=1,
            subtotal_minor=0,
            total_minor=0,
            parking_note="Lot B",
            vehicle_plate="B 1",
            vehicle_model="Kia",
            vehicle_colour="Red",
        )

        assert order.restaurant_id == conversation.restaurant_id

    def test_it_cannot_name_another_restaurant_than_its_conversation(self) -> None:
        conversation = make_conversation(make_restaurant("cafe-a"))

        with pytest.raises(ValidationError) as error:
            Order.objects.create(
                restaurant=make_restaurant("cafe-b"),
                customer=conversation.customer,
                conversation=conversation,
                number=1,
                subtotal_minor=0,
                total_minor=0,
                parking_note="Lot B",
                vehicle_plate="B 1",
                vehicle_model="Kia",
                vehicle_colour="Red",
            )
        assert "conversation" in error.value.message_dict

    def test_it_cannot_name_another_customer_than_its_conversation(self) -> None:
        conversation = make_conversation()
        stranger = make_customer("omar@example.com", "Omar")

        with pytest.raises(ValidationError) as error:
            Order.objects.create(
                restaurant=conversation.restaurant,
                customer=stranger,
                conversation=conversation,
                number=1,
                subtotal_minor=0,
                total_minor=0,
                parking_note="Lot B",
                vehicle_plate="B 1",
                vehicle_model="Kia",
                vehicle_colour="Red",
            )
        assert "customer" in error.value.message_dict

    def test_one_conversation_creates_at_most_one_order(self) -> None:
        conversation = make_conversation()
        make_order(conversation=conversation)

        with pytest.raises(IntegrityError), transaction.atomic():
            make_order(conversation=conversation, number=2)

    def test_the_conversation_reaches_its_order(self) -> None:
        order = make_order()

        assert order.conversation.order == order

    def test_a_number_is_used_once_per_restaurant(self) -> None:
        restaurant = make_restaurant("cafe-a")
        make_order(restaurant, number=1)

        with pytest.raises(IntegrityError), transaction.atomic():
            make_order(restaurant, number=1)

    def test_two_restaurants_each_have_their_own_number_one(self) -> None:
        make_order(make_restaurant("cafe-a"), number=1)
        make_order(make_restaurant("cafe-b"), number=1)

        assert Order.objects.filter(number=1).count() == 2

    def test_the_status_is_one_of_the_eight(self) -> None:
        assert {s.value for s in OrderStatus} == {
            "placed",
            "accepted",
            "rejected",
            "ready",
            "delivered",
            "cancelled",
            "not_found",
            "no_show",
        }
        order = make_order()
        order.status = "lost"
        with pytest.raises(ValidationError) as error:
            order.full_clean()
        assert "status" in error.value.message_dict

    def test_the_wait_time_is_five_ten_or_fifteen(self) -> None:
        order = make_order()
        for minutes in (5, 10, 15):
            order.eta_minutes = minutes
            order.full_clean()
        order.eta_minutes = 7
        with pytest.raises(ValidationError) as error:
            order.full_clean()
        assert "eta_minutes" in error.value.message_dict

    def test_the_car_and_the_parking_note_are_required(self) -> None:
        order = make_order()
        for field in (
            "parking_note",
            "vehicle_plate",
            "vehicle_model",
            "vehicle_colour",
        ):
            setattr(order, field, "")
            with pytest.raises(ValidationError) as error:
                order.full_clean()
            assert field in error.value.message_dict
            order.refresh_from_db()

    def test_the_note_is_optional(self) -> None:
        order = make_order()

        order.full_clean()
        assert order.customer_note == ""

    def test_the_amounts_are_not_negative(self) -> None:
        order = make_order()
        order.total_minor = -1

        with pytest.raises(ValidationError) as error:
            order.full_clean()
        assert "total_minor" in error.value.message_dict

    def test_a_position_needs_both_coordinates(self) -> None:
        with pytest.raises(ValidationError):
            make_order(customer_lat=25.2)

    def test_a_position_is_kept_with_its_distances(self) -> None:
        now = timezone.now()
        order = make_order(
            customer_lat=25.2001,
            customer_lng=55.2701,
            location_accuracy_m=15,
            location_source="gps",
            location_captured_at=now,
            distance_m=85,
        )
        order.refresh_from_db()

        assert (order.customer_lat, order.customer_lng) == (25.2001, 55.2701)
        assert order.distance_m == 85

    def test_a_position_stays_on_earth(self) -> None:
        for field, value in (
            ("customer_lat", 91),
            ("customer_lng", 181),
            ("location_accuracy_m", -1),
        ):
            order = make_order()
            order.customer_lat = order.customer_lng = 0
            setattr(order, field, value)
            with pytest.raises(ValidationError) as error:
                order.full_clean()
            assert field in error.value.message_dict

    def test_a_rejected_order_has_a_reason(self) -> None:
        order = make_order(
            status=OrderStatus.REJECTED,
            rejection_reason_code=RejectionReason.TOO_BUSY,
        )

        assert order.rejection_reason_code == "too_busy"
        with pytest.raises(IntegrityError), transaction.atomic():
            make_order(status=OrderStatus.REJECTED)

    def test_only_a_rejected_order_has_a_reason(self) -> None:
        with pytest.raises(IntegrityError), transaction.atomic():
            make_order(rejection_reason_code=RejectionReason.TOO_FAR)

    def test_the_reason_other_needs_a_note(self) -> None:
        with pytest.raises(IntegrityError), transaction.atomic():
            make_order(
                status=OrderStatus.REJECTED,
                rejection_reason_code=RejectionReason.OTHER,
            )
        order = make_order(
            status=OrderStatus.REJECTED,
            rejection_reason_code=RejectionReason.OTHER,
            rejection_note="Machine broken",
        )
        assert order.rejection_note == "Machine broken"

    def test_the_rejection_note_has_at_most_200_characters(self) -> None:
        order = make_order(
            status=OrderStatus.REJECTED,
            rejection_reason_code=RejectionReason.OTHER,
            rejection_note="x" * 200,
        )
        order.rejection_note = "x" * 201

        with pytest.raises(ValidationError) as error:
            order.full_clean()
        assert "rejection_note" in error.value.message_dict

    def test_the_reasons_are_the_six_of_the_contract(self) -> None:
        assert {r.value for r in RejectionReason} == {
            "item_unavailable",
            "too_busy",
            "closing_soon",
            "too_far",
            "location_unclear",
            "other",
        }

    @pytest.mark.parametrize(
        ("distance_m", "band"),
        [
            (None, DistanceBand.UNKNOWN),
            (0, DistanceBand.IN_LOT),
            (300, DistanceBand.IN_LOT),
            (301, DistanceBand.NEAR),
            (900, DistanceBand.NEAR),
            (901, DistanceBand.FAR),
        ],
    )
    def test_the_distance_band_comes_from_the_restaurants_service_distance(
        self, distance_m: int | None, band: DistanceBand
    ) -> None:
        restaurant = make_restaurant("cafe-a", service_radius_m=300)
        order = make_order(restaurant, distance_m=distance_m)

        assert order.distance_band == band

    def test_a_restaurant_with_no_service_distance_uses_the_default_for_the_label(
        self,
    ) -> None:
        restaurant = make_restaurant("cafe-a")
        near = make_order(restaurant, distance_m=500)

        assert restaurant.service_radius_m is None
        assert near.distance_band == DistanceBand.NEAR

    def test_a_restaurant_with_orders_cannot_be_deleted(self) -> None:
        order = make_order()

        with pytest.raises(ProtectedError):
            order.restaurant.delete()

    def test_a_customer_with_orders_cannot_be_deleted(self) -> None:
        order = make_order()

        with pytest.raises(ProtectedError):
            order.customer.delete()

    def test_a_conversation_with_an_order_cannot_be_deleted(self) -> None:
        order = make_order()

        with pytest.raises(ProtectedError):
            order.conversation.delete()

    def test_a_restaurant_only_sees_its_own_orders(self) -> None:
        a, b = make_restaurant("cafe-a"), make_restaurant("cafe-b")
        in_a = make_order(a)
        make_order(b)

        assert list(Order.objects.for_restaurant(a)) == [in_a]

    def test_the_customer_reaches_their_orders(self) -> None:
        order = make_order()

        assert list(order.customer.orders.all()) == [order]


class TestOrderItem:
    def test_it_keeps_the_names_and_the_price_it_was_given(self) -> None:
        order = make_order()
        item = make_order_item(
            order,
            options=[{"name_en": "Large", "name_ar": "كبير", "price_delta_minor": 100}],
            note="less sugar",
        )
        item.refresh_from_db()

        assert str(item) == "2 x Karak tea"
        assert item.name_ar == "شاي كرك"
        assert item.unit_price_minor == 300
        assert item.line_total_minor == 600
        assert item.options[0]["price_delta_minor"] == 100
        assert item.note == "less sugar"

    def test_it_belongs_to_its_orders_restaurant(self) -> None:
        order = make_order()

        assert make_order_item(order).restaurant_id == order.restaurant_id

    def test_it_cannot_name_another_restaurant(self) -> None:
        order = make_order(make_restaurant("cafe-a"))

        with pytest.raises(ValidationError) as error:
            make_order_item(order, restaurant=make_restaurant("cafe-b"))
        assert "order" in error.value.message_dict

    def test_lines_come_in_order(self) -> None:
        order = make_order()
        for line in (3, 1, 2):
            make_order_item(order, line=line)

        assert [i.line for i in order.items.all()] == [1, 2, 3]

    def test_a_line_number_is_used_once_per_order(self) -> None:
        order = make_order()
        make_order_item(order, line=1)

        with pytest.raises(IntegrityError), transaction.atomic():
            make_order_item(order, line=1)

    def test_the_total_is_the_price_times_the_quantity(self) -> None:
        order = make_order()

        with pytest.raises(IntegrityError), transaction.atomic():
            make_order_item(order, line_total_minor=601)

    @pytest.mark.parametrize("quantity", [0, 21])
    def test_the_quantity_is_one_to_twenty(self, quantity: int) -> None:
        item = make_order_item(make_order())
        item.quantity = quantity

        with pytest.raises(ValidationError) as error:
            item.full_clean()
        assert "quantity" in error.value.message_dict

    def test_the_quantity_limit_is_also_a_database_rule(self) -> None:
        order = make_order()

        with pytest.raises(IntegrityError), transaction.atomic():
            OrderItem.objects.bulk_create(
                [
                    OrderItem(
                        order=order,
                        restaurant=order.restaurant,
                        line=1,
                        name_en="x",
                        name_ar="x",
                        unit_price_minor=100,
                        quantity=21,
                        line_total_minor=2100,
                    )
                ]
            )

    def test_the_options_are_a_list_of_objects(self) -> None:
        order = make_order()

        for bad in ({"a": 1}, ["Large"]):
            with pytest.raises(ValidationError) as error:
                make_order_item(order, options=bad)
            assert "options" in error.value.message_dict

    def test_the_menu_item_is_optional_and_stays_linked(self) -> None:
        order = make_order()
        menu_item = make_item(make_category(order.restaurant))
        linked = make_order_item(order, line=1, menu_item=menu_item)
        free = make_order_item(order, line=2)

        assert linked.menu_item == menu_item
        assert free.menu_item is None

    def test_an_ordered_menu_item_cannot_be_deleted(self) -> None:
        order = make_order()
        menu_item = make_item(make_category(order.restaurant))
        make_order_item(order, menu_item=menu_item)

        with pytest.raises(ProtectedError):
            menu_item.delete()

    def test_its_prices_do_not_follow_the_menu(self) -> None:
        order = make_order()
        menu_item = make_item(make_category(order.restaurant), price_minor=300)
        line = make_order_item(order, menu_item=menu_item)

        menu_item.price_minor = 900
        menu_item.name_en = "Renamed"
        menu_item.save()
        line.refresh_from_db()

        assert (line.unit_price_minor, line.name_en) == (300, "Karak tea")

    def test_a_restaurant_only_sees_its_own_items(self) -> None:
        a, b = make_restaurant("cafe-a"), make_restaurant("cafe-b")
        in_a = make_order_item(make_order(a))
        make_order_item(make_order(b))

        assert list(OrderItem.objects.for_restaurant(a)) == [in_a]


class TestOrderEvent:
    def test_the_creating_event_has_no_from_status(self) -> None:
        order = make_order()
        event = make_event(order)

        assert event.from_status == ""
        assert event.to_status == "placed"
        assert event.actor_id is None
        assert event.created_at is not None
        assert str(event) == f"{order}: - -> placed"

    def test_it_belongs_to_its_orders_restaurant(self) -> None:
        order = make_order()

        assert make_event(order).restaurant_id == order.restaurant_id

    def test_it_cannot_name_another_restaurant(self) -> None:
        order = make_order(make_restaurant("cafe-a"))

        with pytest.raises(ValidationError):
            make_event(order, restaurant=make_restaurant("cafe-b"))

    def test_events_come_in_the_order_they_happened(self) -> None:
        order = make_order()
        staff_id = uuid.uuid4()
        make_event(order, "placed")
        make_event(
            order,
            "accepted",
            from_status="placed",
            actor_type="staff",
            actor_id=staff_id,
        )
        make_event(
            order,
            "ready",
            from_status="accepted",
            actor_type="staff",
            actor_id=staff_id,
        )

        assert [e.to_status for e in order.events.all()] == [
            "placed",
            "accepted",
            "ready",
        ]

    def test_a_staff_member_or_customer_is_named(self) -> None:
        order = make_order()

        for actor_type in ("staff", "customer"):
            with pytest.raises(IntegrityError), transaction.atomic():
                make_event(order, actor_type=actor_type)
            make_event(order, actor_type=actor_type, actor_id=uuid.uuid4())

    def test_the_system_names_nobody(self) -> None:
        order = make_order()

        with pytest.raises(IntegrityError), transaction.atomic():
            make_event(order, actor_type="system", actor_id=uuid.uuid4())

    def test_the_statuses_and_actor_are_from_their_lists(self) -> None:
        event = OrderEvent(
            order=make_order(),
            from_status="gone",
            to_status="lost",
            actor_type="robot",
        )

        with pytest.raises(ValidationError) as error:
            event.full_clean()
        assert {"from_status", "to_status", "actor_type"} <= set(
            error.value.message_dict
        )

    def test_a_restaurant_only_sees_its_own_events(self) -> None:
        a, b = make_restaurant("cafe-a"), make_restaurant("cafe-b")
        in_a = make_event(make_order(a))
        make_event(make_order(b))

        assert list(OrderEvent.objects.for_restaurant(a)) == [in_a]
