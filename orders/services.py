"""Placing an order, and the restaurant's answer to it.

``place_order`` is the one place an ``Order`` is created. The conversation engine calls it when
the customer confirms the final review. It checks everything again from the database (the
assistant and the app are never trusted), takes the next order number under a lock, copies the
lines, the car, the note and the position into the order so later changes never rewrite it, and
does all of it in one transaction.

``accept_order`` and ``reject_order`` are the state machine of the restaurant's side: a placed
order is answered once, ``mark_order_ready`` moves an accepted order to ready, every other
transition is a ``409 order_invalid_transition``, and each
change writes an ``OrderEvent`` and posts the ``result`` message into the customer's chat, all in
one transaction. ``orders_changed_since`` is the restaurant screen's polling
list.
"""

from datetime import datetime, timedelta
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.fields import ErrorDetail

from chat.models import Conversation, ConversationState
from chat.result import post_order_result
from core.geo import haversine_m
from core.order_types import SUPPORTED_ORDER_TYPES
from customers.models import Vehicle
from customers.services import ensure_phone_verified_for_order
from restaurants.models import Restaurant
from users.models import User

from .car import CAR_FIELDS, clean_car_details, missing_car_fields
from .errors import OrderError, OrderProblem, ProblemCode
from .models import (
    ETA_CHOICES,
    MAX_REJECTION_NOTE,
    ActorType,
    Order,
    OrderEvent,
    OrderItem,
    OrderStatus,
    RejectionReason,
)
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


# --- the restaurant's answer ---------------------------------------------------------------


class OrderInvalidTransition(APIException):  # type: ignore[misc]
    """The order is not waiting for an answer any more (another screen answered it first, or
    the customer cancelled): the screen refetches the order and shows its real state."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "order_invalid_transition"
    default_detail = "The order is no longer waiting for an answer."


def _field_error(field: str, message: str, code: str) -> ValidationError:
    return ValidationError({field: [ErrorDetail(message, code)]})


def _lock_order(order_id: UUID, restaurant: Restaurant, expected: str) -> Order:
    """The restaurant's own order, locked, when it is in the ``expected`` state (``placed`` for
    an answer, ``accepted`` for the Ready step).

    An order of another restaurant is a 404, never a 403: the answer must not confirm that it
    exists. Two screens answering together are serialised by the lock, and the second one
    finds the order already answered."""
    try:
        order = (
            Order.objects.for_restaurant(restaurant)
            .select_for_update()
            .get(pk=order_id)
        )
    except Order.DoesNotExist:
        raise NotFound from None
    if order.status != expected:
        raise OrderInvalidTransition
    return order


def _record(order: Order, from_status: str, to_status: str, actor: User) -> None:
    OrderEvent.objects.create(
        restaurant=order.restaurant,
        order=order,
        from_status=from_status,
        to_status=to_status,
        actor_type=ActorType.STAFF,
        actor_id=actor.pk,
    )


def accept_order(
    *, order_id: UUID, restaurant: Restaurant, actor: User, eta_minutes: int
) -> Order:
    """The restaurant accepts a placed order and promises 5, 10 or 15 minutes.

    ``updated_at`` moves with the change (the screens find the order by it), so the fields are
    saved with ``save(update_fields=...)`` and never with ``update()``."""
    if eta_minutes not in {minutes for minutes, _ in ETA_CHOICES}:
        raise _field_error(
            "eta_minutes", "Choose 5, 10 or 15 minutes.", "invalid_choice"
        )
    with transaction.atomic():
        order = _lock_order(order_id, restaurant, OrderStatus.PLACED)
        order.status = OrderStatus.ACCEPTED
        order.eta_minutes = eta_minutes
        order.accepted_at = timezone.now()
        order.save(update_fields=["status", "eta_minutes", "accepted_at", "updated_at"])
        _record(order, OrderStatus.PLACED, OrderStatus.ACCEPTED, actor)
        post_order_result(order)
    return order


def reject_order(
    *,
    order_id: UUID,
    restaurant: Restaurant,
    actor: User,
    reason_code: str,
    note: str = "",
) -> Order:
    """The restaurant rejects a placed order with one of the six reasons. The note is optional
    (at most 200 characters) and required for ``other``."""
    if reason_code not in RejectionReason.values:
        raise _field_error("reason_code", "This reason is not known.", "invalid_choice")
    note = note.strip()
    if len(note) > MAX_REJECTION_NOTE:
        raise _field_error(
            "note",
            f"Use at most {MAX_REJECTION_NOTE} characters.",
            "max_length",
        )
    if reason_code == RejectionReason.OTHER and not note:
        raise _field_error(
            "note", "Say why: a note is required for the reason other.", "required"
        )
    with transaction.atomic():
        order = _lock_order(order_id, restaurant, OrderStatus.PLACED)
        order.status = OrderStatus.REJECTED
        order.rejection_reason_code = reason_code
        order.rejection_note = note
        order.rejected_at = timezone.now()
        order.save(
            update_fields=[
                "status",
                "rejection_reason_code",
                "rejection_note",
                "rejected_at",
                "updated_at",
            ]
        )
        _record(order, OrderStatus.PLACED, OrderStatus.REJECTED, actor)
        post_order_result(order)
    return order


def mark_order_ready(*, order_id: UUID, restaurant: Restaurant, actor: User) -> Order:
    """The restaurant says an accepted order is ready and on its way to the car. Only an
    accepted order can become ready; any other state is ``409 order_invalid_transition``.
    The customer's chat gets the ``result`` message in the same transaction."""
    with transaction.atomic():
        order = _lock_order(order_id, restaurant, OrderStatus.ACCEPTED)
        order.status = OrderStatus.READY
        order.ready_at = timezone.now()
        order.save(update_fields=["status", "ready_at", "updated_at"])
        _record(order, OrderStatus.ACCEPTED, OrderStatus.READY, actor)
        post_order_result(order)
    return order


# --- the restaurant screen's list ----------------------------------------------------------

# The screen sends back the ``server_time`` of its last answer. A change is saved a moment before
# it is committed, so a change that commits just after that time could carry an ``updated_at``
# slightly earlier than it: the list reads from a few seconds before ``since`` so such a change is
# never missed. An order can therefore come twice with the same ``updated_at``; the app merges
# by id and keeps the latest.
CHANGE_OVERLAP = timedelta(seconds=10)
DEFAULT_LOOKBACK = timedelta(hours=24)


def orders_changed_since(
    restaurant: Restaurant, since: datetime | None, now: datetime
) -> list[Order]:
    """The restaurant's orders created or changed after ``since`` (by default in the last 24
    hours), newest first, with their lines. Only that restaurant's rows are ever read."""
    start = (since if since is not None else now - DEFAULT_LOOKBACK) - CHANGE_OVERLAP
    return list(
        Order.objects.for_restaurant(restaurant)
        .filter(updated_at__gt=start)
        .select_related("restaurant")
        .prefetch_related("items")
        .order_by("-placed_at", "-number")
    )
