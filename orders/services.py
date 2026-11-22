"""Placing an order: the one place an ``Order`` is created.

The conversation engine calls ``place_order`` when the customer confirms the final review. It
checks everything again from the database (the assistant and the app are never trusted), takes
the next order number under a lock, copies the lines, the car, the note and the position into
the order so later changes never rewrite it, and does all of it in one transaction.
"""

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from chat.models import Conversation, ConversationState
from core.geo import haversine_m
from core.order_types import SUPPORTED_ORDER_TYPES
from customers.models import Vehicle
from customers.services import ensure_phone_verified_for_order
from restaurants.models import Restaurant

from .car import CAR_FIELDS, clean_car_details, missing_car_fields
from .errors import OrderError, OrderProblem, ProblemCode
from .models import ActorType, Order, OrderEvent, OrderItem, OrderStatus
from .pricing import price_lines


def place_order(conversation: Conversation) -> Order:
    """Create the order of a conversation that is in the review state.

    Raises ``PhoneNotVerified`` (a 403 for the customer) when the phone check is on and the
    customer's phone is not verified, before anything is read or written. Raises ``OrderError``
    for everything else that stops the order; nothing is written then, and the restaurant's
    order number is not used. One conversation creates at most one order.
    """
    ensure_phone_verified_for_order(conversation.customer)

    with transaction.atomic():
        locked = Conversation.objects.select_for_update().get(pk=conversation.pk)
        _check_conversation(locked)
        restaurant = Restaurant.objects.select_for_update().get(pk=locked.restaurant_id)

        priced = price_lines(restaurant, locked.lines)
        said = {
            "parking_note": locked.parking_note,
            "plate": locked.vehicle_plate,
            "model": locked.vehicle_model,
            "colour": locked.vehicle_colour,
        }
        car = clean_car_details(said)
        if car is None:
            raise OrderError(
                [
                    OrderProblem(
                        ProblemCode.CAR_DETAILS_INCOMPLETE,
                        fields=missing_car_fields(said) or CAR_FIELDS,
                    )
                ]
            )

        distance_m = _distance_to_restaurant(locked, restaurant)
        _check_service_distance(restaurant, distance_m)

        number = restaurant.next_order_number
        restaurant.next_order_number = number + 1
        restaurant.save(update_fields=["next_order_number", "updated_at"])

        has_position = locked.location_lat is not None
        order = Order.objects.create(
            restaurant=restaurant,
            customer=locked.customer,
            conversation=locked,
            number=number,
            order_type=locked.order_type,
            subtotal_minor=priced.subtotal_minor,
            total_minor=priced.total_minor,
            customer_note=locked.order_note,
            parking_note=car.parking_note,
            vehicle_plate=car.plate,
            vehicle_model=car.model,
            vehicle_colour=car.colour,
            customer_lat=locked.location_lat,
            customer_lng=locked.location_lng,
            location_accuracy_m=locked.location_accuracy_m if has_position else None,
            location_source=locked.location_source if has_position else "none",
            location_captured_at=locked.location_captured_at if has_position else None,
            distance_m=distance_m,
        )
        OrderItem.objects.bulk_create(
            OrderItem(
                restaurant=restaurant,
                order=order,
                line=line.line,
                menu_item_id=line.item_id,
                name_en=line.name_en,
                name_ar=line.name_ar,
                unit_price_minor=line.unit_price_minor,
                quantity=line.quantity,
                options=[
                    {
                        "name_en": option.name_en,
                        "name_ar": option.name_ar,
                        "price_delta_minor": option.price_delta_minor,
                    }
                    for option in line.options
                ],
                note=line.note,
                line_total_minor=line.line_total_minor,
            )
            for line in priced.lines
        )
        OrderEvent.objects.create(
            restaurant=restaurant,
            order=order,
            from_status="",
            to_status=OrderStatus.PLACED,
            actor_type=ActorType.CUSTOMER,
            actor_id=locked.customer.user_id,
        )
        _remember_vehicle(locked, car.plate, car.model, car.colour)

        now = timezone.now()
        locked.state = ConversationState.PLACED
        locked.closed_at = now
        locked.last_activity_at = now
        locked.save()
    return order


def _check_conversation(conversation: Conversation) -> None:
    if Order.objects.filter(conversation=conversation).exists():
        raise OrderError([OrderProblem(ProblemCode.ALREADY_PLACED)])
    if conversation.is_expired():
        raise OrderError([OrderProblem(ProblemCode.CONVERSATION_EXPIRED)])
    if conversation.state != ConversationState.REVIEW:
        raise OrderError([OrderProblem(ProblemCode.WRONG_STATE)])
    if conversation.order_type not in SUPPORTED_ORDER_TYPES:
        raise OrderError([OrderProblem(ProblemCode.UNSUPPORTED_ORDER_TYPE)])


def _distance_to_restaurant(
    conversation: Conversation, restaurant: Restaurant
) -> int | None:
    """Metres from the customer's position to the restaurant, or ``None`` without a position."""
    lat, lng = conversation.location_lat, conversation.location_lng
    if lat is None or lng is None:
        return None
    return round(haversine_m(lat, lng, restaurant.latitude, restaurant.longitude))


def _check_service_distance(restaurant: Restaurant, distance_m: int | None) -> None:
    """With ``LOCATION_CHECK=enforce``, refuse an order from clearly outside the restaurant's
    service distance. An order without a position, or from a restaurant with no service
    distance, is never refused for its distance: ``warn`` and ``off`` only record it."""
    if settings.LOCATION_CHECK != "enforce":
        return
    radius = restaurant.service_radius_m
    if radius is not None and distance_m is not None and distance_m > radius:
        raise OrderError([OrderProblem(ProblemCode.OUTSIDE_SERVICE_DISTANCE)])


def _remember_vehicle(
    conversation: Conversation, plate: str, model: str, colour: str
) -> None:
    """Save the car so the next conversation can offer it; the order keeps its own copy."""
    Vehicle.objects.update_or_create(
        customer=conversation.customer,
        plate=plate,
        defaults={
            "colour": colour,
            "make_model": model,
            "last_used_at": timezone.now(),
        },
    )
