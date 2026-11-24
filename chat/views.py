"""The chat endpoints (``/api/v1/restaurants/{slug}/conversations``, ``/api/v1/conversations/...``).

Every one needs the customer token and answers ``404`` for a conversation that belongs to
another customer. The views stay thin: the turn itself is ``chat.engine``.
"""

import uuid
from typing import Any

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle, ScopedRateThrottle

from customers.permissions import get_customer
from customers.views import CustomerView
from restaurants.services import public_restaurants

from . import engine
from .serializers import (
    ChatSerializer,
    LocationSerializer,
    MessagesQuerySerializer,
    OpenConversationSerializer,
    SendMessageSerializer,
    VoiceMessageSerializer,
)
from .uploads import AlwaysInMemoryUploadHandler

TAGS = ["chat"]


def _chat(request: Request, result: engine.Sent | engine.Opened) -> dict[str, Any]:
    body = ChatSerializer(
        {"conversation": result.conversation, "messages": result.messages},
        context={"request": request},
    )
    return dict(body.data)


class _ScopedPost(CustomerView):
    """A customer view whose ``POST`` also counts against its own, stricter limit."""

    post_throttle_scope = ""

    def get_throttles(self) -> list[BaseThrottle]:
        throttles: list[BaseThrottle] = super().get_throttles()
        if self.request.method == "POST":
            self.throttle_scope = self.post_throttle_scope
            throttles.append(ScopedRateThrottle())
        return throttles


class OpenConversationView(_ScopedPost):
    post_throttle_scope = "chat_open"

    @extend_schema(
        operation_id="restaurants_conversations_create",
        tags=TAGS,
        summary="Open the conversation with a restaurant",
        description=(
            "Returns the customer's newest conversation with this restaurant when it is placed "
            "or has not expired (`200`, with the whole history from `seq` 1). Otherwise it "
            "starts a new one (`201`): the welcome, one `image` message per menu image and the "
            'first question. `start_new: true` always starts a new one ("Order again"). '
            "`order_type` other than `car` is `400 unsupported_order_type`. A restaurant that "
            "is not visible is a `404`."
        ),
        request=OpenConversationSerializer,
        responses={200: ChatSerializer, 201: ChatSerializer},
    )
    def post(self, request: Request, slug: str) -> Response:
        restaurant = get_object_or_404(public_restaurants(), slug=slug)
        serializer = OpenConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = get_customer(request)
        opened = engine.open_conversation(
            customer,
            restaurant,
            locale=serializer.validated_data.get("locale") or customer.locale,
            start_new=serializer.validated_data["start_new"],
            order_type=serializer.validated_data["order_type"],
        )
        code = status.HTTP_201_CREATED if opened.created else status.HTTP_200_OK
        return Response(_chat(request, opened), status=code)


class ConversationMessagesView(_ScopedPost):
    """Polling list: it keeps its own shape and is not paginated (docs/api-conventions.md)."""

    post_throttle_scope = "chat_message"

    @extend_schema(
        operation_id="conversations_messages_list",
        tags=TAGS,
        summary="Read the messages of a conversation",
        description=(
            "The messages with a `seq` greater than `after_seq`, oldest first, with the "
            "conversation. The app polls this every few seconds and appends by `seq`. It is not "
            "paginated. Another customer's conversation is a `404`."
        ),
        parameters=[MessagesQuerySerializer],
        responses={200: ChatSerializer},
    )
    def get(self, request: Request, id: uuid.UUID) -> Response:
        query = MessagesQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = engine.list_messages(
            get_customer(request), id, query.validated_data["after_seq"]
        )
        return Response(_chat(request, result))

    @extend_schema(
        operation_id="conversations_messages_create",
        tags=TAGS,
        summary="Send a message or tap a button",
        description=(
            "One customer input: `text` (at most 500 characters) or an `action`, never both. "
            "The answer holds the customer's own message and the bot's replies, always `201`; "
            "sending the same `client_message_id` again returns the first result, also `201`. "
            "A missing or invalid answer is handled by the bot in the conversation, not as an "
            "error. An action that is not allowed at this step is `409 "
            "invalid_action_for_state`; a conversation past its expiry is `409 "
            "conversation_expired`."
        ),
        request=SendMessageSerializer,
        responses={201: ChatSerializer},
    )
    def post(self, request: Request, id: uuid.UUID) -> Response:
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        customer = get_customer(request)
        if "text" in data:
            result = engine.send_text(
                customer, id, data["client_message_id"], data["text"]
            )
        else:
            action = engine.Action(
                name=data["action"],
                field_name=data.get("field", ""),
                value=str(data.get("value", "")),
                locale=data.get("locale", ""),
                lines=data.get("lines", []),
            )
            result = engine.send_action(customer, id, data["client_message_id"], action)
        return Response(_chat(request, result), status=status.HTTP_201_CREATED)


class ConversationVoiceView(_ScopedPost):
    post_throttle_scope = "chat_message"
    parser_classes = [MultiPartParser]  # noqa: RUF012

    def initialize_request(self, request: Any, *args: Any, **kwargs: Any) -> Request:
        # The clip is read into memory and never written to the disk, whatever its size.
        request.upload_handlers = [AlwaysInMemoryUploadHandler(request)]
        return super().initialize_request(request, *args, **kwargs)

    @extend_schema(
        operation_id="conversations_voice_create",
        tags=TAGS,
        summary="Send a voice message",
        description=(
            "One WAV clip of at most 60 seconds and 5 MB, with a `client_message_id`. The clip is "
            "read in memory, understood like a typed message and dropped: it is never stored, and "
            "only what was said stays on the customer's message (`used_voice: true` and the "
            "`transcript`). The answer is the same as for a message, always `201`, and a replay "
            "of the same `client_message_id` returns the first result. A clip nobody could "
            "understand, and an assistant that is down, are not errors: the customer's message is "
            "stored with an empty transcript and the bot answers in the chat (the second also "
            "makes `ai_available` false for a few minutes). `400` codes: `audio_too_long`, "
            "`audio_too_large` (the clip above 5 MB, or the whole request above 6 MB) and "
            "`unsupported_audio_format` (only WAV for now). Taken in every open step (the "
            "order, the car, the note and the review); a placed conversation is `409 "
            "invalid_action_for_state` and an expired one `409 conversation_expired`. A spoken "
            "yes at the review places the order, so `403 phone_not_verified` is possible there."
        ),
        request={"multipart/form-data": VoiceMessageSerializer},
        responses={201: ChatSerializer},
    )
    def post(self, request: Request, id: uuid.UUID) -> Response:
        serializer = VoiceMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = engine.send_voice(
            get_customer(request),
            id,
            serializer.validated_data["client_message_id"],
            serializer.validated_data["audio"],
        )
        return Response(_chat(request, result), status=status.HTTP_201_CREATED)


class ConversationLocationView(CustomerView):
    @extend_schema(
        operation_id="conversations_location_update",
        tags=TAGS,
        summary="Send the phone's position",
        description=(
            "The phone's position, sent by the app when the car question appears. It is kept on "
            "the conversation until the order is placed, the latest value wins, and it goes to "
            "the restaurant's staff with the order. `204` with no body. Allowed in any open "
            "step; a placed conversation is `409 invalid_action_for_state` and an expired one "
            "`409 conversation_expired`. A latitude outside -90 to 90, a longitude outside -180 "
            "to 180 or a negative `accuracy_m` is `400 invalid_location`. Another customer's "
            "conversation is a `404`."
        ),
        request=LocationSerializer,
        responses={204: None},
    )
    def put(self, request: Request, id: uuid.UUID) -> Response:
        serializer = LocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        engine.set_location(
            get_customer(request),
            id,
            lat=data["lat"],
            lng=data["lng"],
            accuracy_m=data.get("accuracy_m"),
            source=data["source"],
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
