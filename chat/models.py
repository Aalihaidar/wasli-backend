from datetime import datetime, timedelta
from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from core.geo import LOCATION_SOURCE_CHOICES, LocationSource
from core.locales import LOCALE_CHOICES, Locale
from core.tenancy import RestaurantOwnedModel, align_with_parent

# A conversation that has not reached ``placed`` expires this long after the customer's last
# message; the engine moves ``expires_at`` forward on every customer message.
IDLE_EXPIRY = timedelta(minutes=60)

_latitude_validators = [MinValueValidator(-90), MaxValueValidator(90)]
_longitude_validators = [MinValueValidator(-180), MaxValueValidator(180)]


def default_expiry() -> datetime:
    return timezone.now() + IDLE_EXPIRY


class ConversationState(models.TextChoices):
    ORDERING = "ordering", "Ordering"
    ASK_CAR = "ask_car", "Asking for the car"
    ASK_NOTE = "ask_note", "Asking for a note"
    REVIEW = "review", "Review"
    PLACED = "placed", "Placed"


class CarField(models.TextChoices):
    """The car details the bot asks for one at a time when the assistant is unavailable."""

    PARKING_NOTE = "parking_note", "Parking note"
    PLATE = "plate", "Plate"
    MODEL = "model", "Model"
    COLOUR = "colour", "Colour"


class Sender(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    BOT = "bot", "Bot"
    SYSTEM = "system", "System"


class MessageKind(models.TextChoices):
    TEXT = "text", "Text"
    IMAGE = "image", "Image"
    ORDER_SUMMARY = "order_summary", "Order summary"
    REVIEW = "review", "Review"
    RESULT = "result", "Result"


class Conversation(RestaurantOwnedModel):
    """One customer's chat with one restaurant, from the welcome to the placed order.

    The engine keeps everything it needs between messages here: the order lines being built,
    the question the bot is waiting on, the car details, the note and the position. The
    customer-facing text is never stored on this row; it lives in ``Message`` rows. The
    order itself is a separate ``orders.Order`` linked one-to-one to the conversation.
    """

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="conversations"
    )
    state = models.CharField(
        max_length=20,
        choices=ConversationState,
        default=ConversationState.ORDERING,
    )
    # The language the bot writes in; the customer can switch it in the chat.
    locale = models.CharField(
        max_length=2, choices=LOCALE_CHOICES, default=Locale.EN.value
    )
    # A list of ``{line, item_id, quantity, option_ids, note}``; the server prices it.
    lines = models.JSONField(default=list, blank=True)
    # The choice the bot asked (which burger, which size) while it waits for an answer.
    pending_question = models.JSONField(null=True, blank=True)
    # The car field being asked on its own when the assistant is unavailable.
    pending_field = models.CharField(max_length=20, choices=CarField, blank=True)
    # Set while the customer edits one part of the review, so the next step returns to it.
    return_to_review = models.BooleanField(default=False)
    parking_note = models.CharField(max_length=200, blank=True)
    vehicle_plate = models.CharField(max_length=20, blank=True)
    vehicle_model = models.CharField(max_length=40, blank=True)
    vehicle_colour = models.CharField(max_length=30, blank=True)
    order_note = models.CharField(max_length=300, blank=True)
    # The customer's position. Personal data: shown only to that restaurant's staff and the
    # customer, never logged and never sent to the assistant.
    location_lat = models.FloatField(
        null=True, blank=True, validators=_latitude_validators
    )
    location_lng = models.FloatField(
        null=True, blank=True, validators=_longitude_validators
    )
    location_accuracy_m = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(0)]
    )
    location_source = models.CharField(
        max_length=10,
        choices=LOCATION_SOURCE_CHOICES,
        default=LocationSource.NONE.value,
    )
    location_captured_at = models.DateTimeField(null=True, blank=True)
    # The seq of the newest message; the next message takes ``last_seq + 1``.
    last_seq = models.PositiveIntegerField(default=0, editable=False)
    last_activity_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(default=default_expiry)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-last_activity_at",)
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=["restaurant", "customer", "-last_activity_at"],
                name="conversation_current_idx",
            )
        ]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=(
                    models.Q(location_lat__isnull=True, location_lng__isnull=True)
                    | models.Q(location_lat__isnull=False, location_lng__isnull=False)
                ),
                name="conversation_location_complete",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.restaurant}: {self.customer} ({self.state})"

    def is_expired(self, now: datetime | None = None) -> bool:
        return (now or timezone.now()) >= self.expires_at

    def clean(self) -> None:
        super().clean()
        self._check_shapes()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self._check_shapes()
        super().save(*args, **kwargs)

    def _check_shapes(self) -> None:
        if not isinstance(self.lines, list) or not all(
            isinstance(line, dict) for line in self.lines
        ):
            raise ValidationError({"lines": "The lines must be a list of objects."})
        if self.pending_question is not None and not isinstance(
            self.pending_question, dict
        ):
            raise ValidationError(
                {"pending_question": "The pending question must be an object."}
            )
        if (self.location_lat is None) != (self.location_lng is None):
            raise ValidationError(
                {"location_lat": "Latitude and longitude go together."}
            )


class Message(RestaurantOwnedModel):
    """One message in a conversation. Append-only: messages are never edited, and they are
    shown in ``seq`` order. The text is already written in the conversation's language."""

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    seq = models.PositiveIntegerField()
    sender = models.CharField(max_length=10, choices=Sender)
    kind = models.CharField(
        max_length=15, choices=MessageKind, default=MessageKind.TEXT
    )
    text = models.TextField(blank=True)
    # What the assistant heard, for a voice message. The audio itself is never stored.
    transcript = models.TextField(blank=True)
    used_voice = models.BooleanField(default=False)
    # A menu image the bot sends; it names a file already stored for the restaurant's menu
    # images, so nothing is uploaded here.
    image = models.ImageField(upload_to="chat/messages/", blank=True)
    # ``summary``, ``quick_replies``, the review fields or the result of an order.
    payload = models.JSONField(default=dict, blank=True)
    # Sent by the customer's app with every message, so a retry never duplicates it.
    client_message_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ("conversation", "seq")
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["conversation", "seq"], name="unique_seq_per_conversation"
            ),
            models.UniqueConstraint(
                fields=["conversation", "client_message_id"],
                condition=models.Q(client_message_id__isnull=False),
                name="unique_client_message_id_per_conversation",
            ),
        ]

    def __str__(self) -> str:
        return f"#{self.seq} {self.sender} {self.kind}"

    def clean(self) -> None:
        super().clean()
        self._normalise()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self._normalise()
        super().save(*args, **kwargs)

    def _normalise(self) -> None:
        if self.conversation_id is not None:
            align_with_parent(self, self.conversation, "conversation")
        if not isinstance(self.payload, dict):
            raise ValidationError({"payload": "The payload must be an object."})
