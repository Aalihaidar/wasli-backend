"""Small helpers that build valid order rows for tests (invented data only)."""

from chat.models import Conversation
from chat.tests.factories import make_conversation
from customers.models import Customer
from menu.models import MenuItem
from orders.models import Order, OrderEvent, OrderItem
from restaurants.models import Restaurant


def make_order(
    restaurant: Restaurant | None = None,
    customer: Customer | None = None,
    conversation: Conversation | None = None,
    **extra: object,
) -> Order:
    """A placed order with a valid car and no position. The restaurant and customer are those
    of the conversation, which is made when not given, so several calls in one test never
    clash on a slug, an email or an order number."""
    conversation = conversation or make_conversation(restaurant, customer)
    values: dict[str, object] = {
        "number": Order.objects.for_restaurant(conversation.restaurant).count() + 1,
        "subtotal_minor": 600,
        "total_minor": 600,
        "parking_note": "Parking B2 near the lift",
        "vehicle_plate": "A 12345",
        "vehicle_model": "Toyota Camry",
        "vehicle_colour": "White",
        **extra,
    }
    return Order.objects.create(
        restaurant=conversation.restaurant,
        customer=conversation.customer,
        conversation=conversation,
        **values,
    )


def make_order_item(
    order: Order,
    line: int = 1,
    menu_item: MenuItem | None = None,
    **extra: object,
) -> OrderItem:
    values: dict[str, object] = {
        "name_en": "Karak tea",
        "name_ar": "شاي كرك",
        "unit_price_minor": 300,
        "quantity": 2,
        "line_total_minor": 600,
        **extra,
    }
    return OrderItem.objects.create(
        order=order, line=line, menu_item=menu_item, **values
    )


def make_event(order: Order, to_status: str = "placed", **extra: object) -> OrderEvent:
    values: dict[str, object] = {"actor_type": "system", **extra}
    return OrderEvent.objects.create(order=order, to_status=to_status, **values)
