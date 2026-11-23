"""The conversation engine: what the bot does with each thing a customer sends.

One customer input is one *turn*. A turn runs in a single transaction that holds the
conversation's row lock, so two taps at once never interleave, a retry with the same
``client_message_id`` returns the first result instead of running again, and a failure leaves no
half-written conversation. The turn stores the customer's message, decides what to do (the
assistant only helps to understand what the customer meant), updates the conversation and writes
the bot's replies. Every word the bot says comes from ``chat/texts.py``; every price from the
order service.

This module covers the start of a conversation and the ordering step up to the order summary and
the customer's confirmation. The steps after it (the car question, the note, the review and
placing the order) are added with their own endpoints; until then a conversation that has moved on
accepts only a language change and a restart.
"""

import uuid
from collections.abc import Callable
from typing import Any, NamedTuple

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from assistant.models import Outcome
from assistant.services import Assistant
from assistant.types import (
    AudioInput,
)
from core.locales import Locale
from core.order_types import SUPPORTED_ORDER_TYPES
from customers.models import Customer
from orders.errors import OrderError, ProblemCode
from restaurants.models import Restaurant, RestaurantMenuImage

from .errors import ConversationExpired, InvalidActionForState, UnsupportedOrderType
from .models import (
    IDLE_EXPIRY,
    Conversation,
    ConversationState,
    Message,
    MessageKind,
    Sender,
)
from .replies import Action, Reply
from .services import add_message
from .steps import Turn
from .texts import pick, say

# A provider failure of these kinds turns the assistant off for a few minutes. A badly formed
# answer (``invalid_output``) does not: the provider is up, it just did not understand.
_OUTAGE = {Outcome.ERROR, Outcome.TIMEOUT, Outcome.RATE_LIMITED}
# What a provider answers when it cannot read the clip itself (a corrupt or unsupported file):
# the clip is the problem, so the customer is asked to say it again and the assistant stays on.
_UNREADABLE_AUDIO = {"http_400", "http_413", "http_415", "http_422"}
# What the bot quotes of a thing the customer asked for that is not on the menu.
_UNMATCHED_SHOWN = 3
_UNMATCHED_CHARS = 60
_MAX_NOTE_CHARS = 200

# The actions of the contract and the steps each is allowed in. ``set_locale`` and ``restart`` work
# in every open step. Anything else is ``409 invalid_action_for_state``.
_ALLOWED_ACTIONS: dict[str, set[str]] = {
    ConversationState.ORDERING: {
        "confirm",
        "edit",
        "choose",
        "set_lines",
        "set_locale",
        "restart",
    },
    ConversationState.ASK_CAR: {"set_locale", "restart"},
    ConversationState.ASK_NOTE: {"skip_note", "set_locale", "restart"},
    ConversationState.REVIEW: {
        "confirm",
        "edit",
        "edit_field",
        "set_locale",
        "restart",
    },
}


# The button label of each part of the order that can be edited from the review.
_FIELD_LABELS = {"items": "order", "car": "car", "note": "note"}


def get_assistant() -> Assistant:
    """The assistant layer for a turn (a test replaces this with a scripted fake)."""
    return Assistant()


class Opened(NamedTuple):
    conversation: Conversation
    messages: list[Message]
    created: bool


class Sent(NamedTuple):
    conversation: Conversation
    messages: list[Message]


def _owned(
    customer: Customer, conversation_id: uuid.UUID, *, lock: bool
) -> Conversation:
    """The customer's own conversation. Another customer's, or an unknown id, is a 404."""
    query = Conversation.objects.select_related("restaurant", "customer", "order")
    if lock:
        query = query.select_for_update(of=("self",))
    try:
        return query.get(pk=conversation_id, customer=customer)
    except Conversation.DoesNotExist:
        raise NotFound from None


def _store(conversation: Conversation, reply: Reply) -> Message:
    return add_message(
        conversation,
        Sender.BOT,
        MessageKind(reply.kind),
        text=reply.text,
        image=reply.image,
        payload=reply.payload,
    )


def _replayed(conversation: Conversation, first: Message) -> list[Message]:
    """What a request produced the first time: the customer's message and the bot's replies
    that follow it, up to the customer's next message."""
    following = Message.objects.filter(conversation=conversation, seq__gt=first.seq)
    next_customer = (
        following.filter(sender=Sender.CUSTOMER)
        .order_by("seq")
        .values_list("seq", flat=True)
    ).first()
    if next_customer is not None:
        following = following.filter(seq__lt=next_customer)
    return [first, *following.order_by("seq")]


def _run_turn(
    customer: Customer,
    conversation_id: uuid.UUID,
    client_message_id: uuid.UUID,
    *,
    allowed: Callable[[Conversation], None],
    customer_message: Callable[[Turn], tuple[str, dict[str, Any]]],
    handler: Callable[[Turn], list[Reply]],
    used_voice: bool = False,
) -> Sent:
    with transaction.atomic():
        conversation = _owned(customer, conversation_id, lock=True)
        earlier = Message.objects.filter(
            conversation=conversation, client_message_id=client_message_id
        ).first()
        if earlier is not None:
            return Sent(conversation, _replayed(conversation, earlier))

        if conversation.state == ConversationState.PLACED:
            raise InvalidActionForState
        if conversation.is_expired():
            raise ConversationExpired
        allowed(conversation)

        turn = Turn(conversation, get_assistant())
        text, payload = customer_message(turn)
        stored = [
            add_message(
                conversation,
                Sender.CUSTOMER,
                MessageKind.TEXT,
                text=text,
                used_voice=used_voice,
                payload=payload,
                client_message_id=client_message_id,
            )
        ]
        turn.customer_row = stored[0]
        now = timezone.now()
        conversation.last_activity_at = now
        conversation.expires_at = now + IDLE_EXPIRY
        try:
            replies = handler(turn)
        except OrderError as error:
            if ProblemCode.RESTAURANT_UNAVAILABLE not in error.codes:
                raise
            replies = [turn.reply("restaurant_unavailable")]
        stored.extend(_store(conversation, reply) for reply in replies)
        conversation.save()
        return Sent(conversation, stored)


def send_text(
    customer: Customer,
    conversation_id: uuid.UUID,
    client_message_id: uuid.UUID,
    text: str,
) -> Sent:
    """The customer typed ``text``. In ``ordering`` the assistant reads it as an order change."""

    def allowed(conversation: Conversation) -> None:
        """Every open step takes a typed or spoken answer."""

    return _run_turn(
        customer,
        conversation_id,
        client_message_id,
        allowed=allowed,
        customer_message=lambda turn: (text, {}),
        handler=lambda turn: turn.on_text(text),
    )


def send_voice(
    customer: Customer,
    conversation_id: uuid.UUID,
    client_message_id: uuid.UUID,
    audio: AudioInput,
) -> Sent:
    """The customer spoke. The clip is understood like a typed message in ``ordering``; the
    customer's message holds what was heard (``transcript``) and never the audio."""

    def allowed(conversation: Conversation) -> None:
        """Every open step takes a typed or spoken answer."""

    return _run_turn(
        customer,
        conversation_id,
        client_message_id,
        allowed=allowed,
        customer_message=lambda turn: ("", {}),
        handler=lambda turn: turn.on_voice(audio),
        used_voice=True,
    )


def send_action(
    customer: Customer,
    conversation_id: uuid.UUID,
    client_message_id: uuid.UUID,
    action: Action,
) -> Sent:
    """The customer tapped a button, or the app sent its own request (the item picker)."""

    def allowed(conversation: Conversation) -> None:
        if action.name not in _ALLOWED_ACTIONS.get(conversation.state, set()):
            raise InvalidActionForState

    def customer_message(turn: Turn) -> tuple[str, dict[str, Any]]:
        payload: dict[str, Any] = {"action": action.name}
        label = ""
        if action.name == "confirm":
            in_review = turn.conversation.state == ConversationState.REVIEW
            label = turn.say("yes_send_label" if in_review else "confirm_label")
        elif action.name == "skip_note":
            label = turn.say("skip_label")
        elif action.name == "edit_field":
            label = turn.say(
                f"edit_{_FIELD_LABELS.get(action.field_name, 'order')}_label"
            )
            payload["field"] = action.field_name
        elif action.name == "edit":
            label = turn.say("edit_label")
        elif action.name == "restart":
            label = turn.say("restart_label")
        elif action.name == "set_lines":
            label = turn.say("picked_items")
        elif action.name == "set_locale":
            label = say("locale_label", action.locale)
            payload["locale"] = action.locale
        elif action.name == "choose":
            label = turn.choice_label(action.value)
            payload["value"] = action.value
        return label, payload

    return _run_turn(
        customer,
        conversation_id,
        client_message_id,
        allowed=allowed,
        customer_message=customer_message,
        handler=lambda turn: turn.on_action(action),
    )


def set_location(
    customer: Customer,
    conversation_id: uuid.UUID,
    *,
    lat: float,
    lng: float,
    accuracy_m: float | None,
    source: str,
) -> None:
    """Keep the customer's position on the conversation until the order is placed; the latest
    value wins. Nothing is said in the chat. The position is personal data: it goes to the
    restaurant's staff with the order and is never logged or sent to the assistant."""
    with transaction.atomic():
        conversation = _owned(customer, conversation_id, lock=True)
        if conversation.state == ConversationState.PLACED:
            raise InvalidActionForState
        if conversation.is_expired():
            raise ConversationExpired
        conversation.location_lat = lat
        conversation.location_lng = lng
        conversation.location_accuracy_m = accuracy_m
        conversation.location_source = source
        conversation.location_captured_at = timezone.now()
        conversation.save(
            update_fields=[
                "location_lat",
                "location_lng",
                "location_accuracy_m",
                "location_source",
                "location_captured_at",
                "updated_at",
            ]
        )


def list_messages(
    customer: Customer, conversation_id: uuid.UUID, after_seq: int = 0
) -> Sent:
    """The messages after ``after_seq``, oldest first (what the app polls)."""
    conversation = _owned(customer, conversation_id, lock=False)
    messages = Message.objects.filter(
        conversation=conversation, seq__gt=after_seq
    ).order_by("seq")
    return Sent(conversation, list(messages))


# --- starting a conversation ------------------------------------------------------------------


def _welcome(restaurant: Restaurant, locale: str) -> str:
    custom = (
        restaurant.welcome_message_ar or restaurant.welcome_message_en
        if locale == Locale.AR.value
        else restaurant.welcome_message_en
    )
    if custom.strip():
        return custom.strip()
    return say(
        "welcome",
        locale,
        restaurant=pick(restaurant.name_en, restaurant.name_ar_display, locale),
    )


@transaction.atomic
def open_conversation(
    customer: Customer,
    restaurant: Restaurant,
    *,
    locale: str,
    start_new: bool = False,
    order_type: str = "car",
) -> Opened:
    """The customer's current conversation with a restaurant, or a new one.

    The newest conversation is returned (with its whole history) while it is placed or has not
    expired; a new one is made when there is none, the last one expired unplaced, or
    ``start_new`` is true. A new conversation already holds the welcome, one message per menu
    image and the first question.
    """
    if order_type not in SUPPORTED_ORDER_TYPES:
        raise UnsupportedOrderType
    # Two requests at once for the same customer take turns, so they never make two.
    Customer.objects.select_for_update().get(pk=customer.pk)
    latest = (
        Conversation.objects.for_restaurant(restaurant)
        .filter(customer=customer)
        .order_by("-created_at")
        .first()
    )
    if (
        latest is not None
        and not start_new
        and (latest.state == ConversationState.PLACED or not latest.is_expired())
    ):
        history = list(latest.messages.order_by("seq"))
        return Opened(latest, history, created=False)

    conversation = Conversation.objects.create(
        restaurant=restaurant,
        customer=customer,
        locale=locale,
        order_type=order_type,
    )
    replies = [Reply(_welcome(restaurant, locale))]
    replies.extend(
        Reply(
            pick(image.caption_en, image.caption_ar_display, locale),
            MessageKind.IMAGE,
            image=image.image.name or "",
        )
        for image in RestaurantMenuImage.objects.for_restaurant(restaurant)
    )
    replies.append(Reply(say("what_to_order", locale)))
    messages = [_store(conversation, reply) for reply in replies]
    return Opened(conversation, messages, created=True)


__all__ = [
    "Action",
    "Opened",
    "Sent",
    "list_messages",
    "open_conversation",
    "send_action",
    "send_text",
    "send_voice",
    "set_location",
]
