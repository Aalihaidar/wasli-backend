"""The shapes of the chat endpoints.

A conversation and its messages are always sent together as ``{conversation, messages}``. The
bot's text is already written in the conversation's language: the app shows ``text`` and renders
``kind`` and ``payload``, and never writes bot text of its own.
"""

from typing import Any, ClassVar

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from assistant.availability import ai_available
from assistant.limits import MAX_LINES, MAX_QUANTITY, MAX_TEXT_CHARS
from core.order_types import OrderType
from customers.serializers import LOCALES

from .audio import read_voice_upload
from .models import Conversation, ConversationState, Message, MessageKind, Sender

# The buttons and requests a customer can send. ``edit_field`` and ``skip_note`` belong to the
# car and note steps and are refused (409) until those steps exist.
ACTIONS = [
    "confirm",
    "edit",
    "edit_field",
    "choose",
    "skip_note",
    "set_lines",
    "set_locale",
    "restart",
]
EDIT_FIELDS = ["items", "car", "note"]


class OpenConversationSerializer(serializers.Serializer):  # type: ignore[misc]
    locale = serializers.ChoiceField(
        choices=LOCALES,
        required=False,
        help_text="The language of the bot. Defaults to the customer's own language.",
    )
    start_new = serializers.BooleanField(
        default=False,
        help_text=(
            "True starts a new conversation even when the current one is still open or "
            'placed ("Order again").'
        ),
    )
    order_type = serializers.ChoiceField(
        choices=OrderType.choices,
        default=OrderType.CAR.value,
        help_text="How the order is served. Only `car` is accepted for now.",
    )


class PickedLineSerializer(serializers.Serializer):  # type: ignore[misc]
    """One line of the item picker. Never a price: the server prices every line."""

    item_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_QUANTITY)
    option_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, max_length=20
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=200)


class SendMessageSerializer(serializers.Serializer):  # type: ignore[misc]
    client_message_id = serializers.UUIDField(
        help_text=(
            "Made by the app for every message and kept for a retry: sending it again "
            "returns the first result and never runs twice."
        )
    )
    text = serializers.CharField(
        required=False,
        max_length=MAX_TEXT_CHARS,
        help_text=(
            f"What the customer typed, at most {MAX_TEXT_CHARS} characters (counted as "
            "Unicode code points after trimming). Give this or `action`, not both."
        ),
    )
    action = serializers.ChoiceField(
        choices=ACTIONS,
        required=False,
        help_text="A button the customer tapped. Give this or `text`, not both.",
    )
    field = serializers.ChoiceField(
        choices=EDIT_FIELDS, required=False, help_text="For `edit_field`: what to edit."
    )
    value = serializers.UUIDField(
        required=False,
        help_text="For `choose`: the `value` of the button the customer tapped.",
    )
    lines = PickedLineSerializer(
        many=True,
        required=False,
        allow_empty=True,
        max_length=MAX_LINES,
        help_text="For `set_lines`: the whole order, as the item picker built it.",
    )
    locale = serializers.ChoiceField(
        choices=LOCALES, required=False, help_text="For `set_locale`."
    )

    # What each action needs besides its name.
    _REQUIRES: ClassVar[dict[str, str]] = {
        "edit_field": "field",
        "choose": "value",
        "set_lines": "lines",
        "set_locale": "locale",
    }

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        has_text, has_action = "text" in attrs, "action" in attrs
        if has_text == has_action:
            raise serializers.ValidationError(
                {"text": "Send exactly one of text and action."}, code="text_or_action"
            )
        needed = self._REQUIRES.get(attrs.get("action", ""))
        if needed and needed not in attrs:
            raise serializers.ValidationError(
                {needed: "This is required for this action."}, code="required"
            )
        return attrs


class VoiceMessageSerializer(serializers.Serializer):  # type: ignore[misc]
    client_message_id = serializers.UUIDField(
        help_text="Made by the app for every message and kept for a retry, as for a text."
    )
    audio = serializers.FileField(
        help_text=(
            "One WAV clip of at most 30 seconds and 5 MB. It is read in memory and never "
            "stored: only what was said stays on the message, as its transcript."
        )
    )

    def validate_audio(self, upload: Any) -> Any:
        return read_voice_upload(upload)


class MessagesQuerySerializer(serializers.Serializer):  # type: ignore[misc]
    after_seq = serializers.IntegerField(
        min_value=0,
        default=0,
        help_text="Return only messages whose `seq` is greater than this. 0 returns all.",
    )


class ConversationSerializer(serializers.ModelSerializer):  # type: ignore[misc]
    restaurant_slug = serializers.CharField(source="restaurant.slug", read_only=True)
    locale = serializers.ChoiceField(
        choices=LOCALES, read_only=True, help_text="The language the bot writes in."
    )
    ai_available = serializers.SerializerMethodField(
        help_text=(
            "False while the assistant cannot be used (it failed a moment ago, or it is "
            "off): typed and spoken orders are not understood and the app offers the item "
            "picker."
        )
    )

    class Meta:
        model = Conversation
        fields = (
            "id",
            "restaurant_slug",
            "state",
            "locale",
            "order_type",
            "ai_available",
            "expires_at",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.BooleanField())
    def get_ai_available(self, obj: Conversation) -> bool:
        return ai_available()


class MessageSerializer(serializers.ModelSerializer):  # type: ignore[misc]
    image_url = serializers.ImageField(
        source="image",
        read_only=True,
        use_url=True,
        allow_null=True,
        help_text="The absolute address of the picture of an `image` message, or null.",
    )
    transcript = serializers.SerializerMethodField(
        help_text=(
            "What the assistant heard, for a voice message (empty when it could not "
            "understand the clip); null for typed text. The audio is never stored."
        )
    )

    class Meta:
        model = Message
        fields = (
            "id",
            "seq",
            "sender",
            "kind",
            "text",
            "image_url",
            "transcript",
            "used_voice",
            "payload",
            "created_at",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_transcript(self, obj: Message) -> str | None:
        return obj.transcript if obj.used_voice else None


class ChatSerializer(serializers.Serializer):  # type: ignore[misc]
    """What every chat endpoint answers: the conversation and some of its messages."""

    conversation = ConversationSerializer()
    messages = MessageSerializer(many=True)


# Documented here so the message ``kind`` and ``state`` lists are named in the schema.
__all__ = [
    "ChatSerializer",
    "ConversationState",
    "MessageKind",
    "Sender",
]
