from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from core.geo import (
    LOCATION_SOURCE_CHOICES,
    DistanceBand,
    LocationSource,
    distance_band,
)
from core.money import CURRENCY
from core.tenancy import RestaurantOwnedModel, align_with_parent

# The wait times a restaurant can promise when it accepts an order.
ETA_CHOICES = [(5, "5 minutes"), (10, "10 minutes"), (15, "15 minutes")]
MAX_LINES = 20
MAX_QUANTITY = 20
MAX_REJECTION_NOTE = 200

_latitude_validators = [MinValueValidator(-90), MaxValueValidator(90)]
_longitude_validators = [MinValueValidator(-180), MaxValueValidator(180)]


class OrderStatus(models.TextChoices):
    PLACED = "placed", "Placed"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    READY = "ready", "Ready"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"
    NOT_FOUND = "not_found", "Car not found"
    NO_SHOW = "no_show", "No-show"


class RejectionReason(models.TextChoices):
    ITEM_UNAVAILABLE = "item_unavailable", "Item unavailable"
    TOO_BUSY = "too_busy", "Too busy"
    CLOSING_SOON = "closing_soon", "Closing soon"
    TOO_FAR = "too_far", "Customer is too far"
    LOCATION_UNCLEAR = "location_unclear", "Location unclear"
    OTHER = "other", "Other"


class FulfilmentType(models.TextChoices):
    CAR = "car", "To the car"


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    CARD = "card", "Card"


class ActorType(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    STAFF = "staff", "Staff"
    SYSTEM = "system", "System"


class Order(RestaurantOwnedModel):
    """An order a customer confirmed at the end of a conversation.

    Created in one transaction by the order service, never by hand. It keeps its own copy
    of everything the customer answered (the car, the note, the position), so a later change
    to the conversation, the customer or the menu never rewrites it. The server computes
    every amount; the client and the assistant never send one.
    """

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="orders"
    )
    # One conversation creates at most one order.
    conversation = models.OneToOneField(
        "chat.Conversation", on_delete=models.PROTECT, related_name="order"
    )
    # Unique per restaurant; taken from ``Restaurant.next_order_number`` under a row lock.
    number = models.PositiveIntegerField()
    status = models.CharField(
        max_length=15, choices=OrderStatus, default=OrderStatus.PLACED
    )
    fulfilment_type = models.CharField(
        max_length=10, choices=FulfilmentType, default=FulfilmentType.CAR
    )
    subtotal_minor = models.PositiveIntegerField(
        help_text="In fils: 1250 is 12.50 AED."
    )
    total_minor = models.PositiveIntegerField(help_text="In fils: 1250 is 12.50 AED.")
    currency = models.CharField(max_length=3, default=CURRENCY, editable=False)
    customer_note = models.CharField(max_length=300, blank=True)
    # Where the car is and which car it is, as the customer said it.
    parking_note = models.CharField(max_length=200)
    vehicle_plate = models.CharField(max_length=20)
    vehicle_model = models.CharField(max_length=40)
    vehicle_colour = models.CharField(max_length=30)
    # The customer's position when the order was placed. Personal data: shown only to that
    # restaurant's staff and the customer, never logged.
    customer_lat = models.FloatField(
        null=True, blank=True, validators=_latitude_validators
    )
    customer_lng = models.FloatField(
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
    # Metres from the customer to the restaurant (shown to staff) and to the parking lot's
    # centre (used by the rules and the distance band). Empty without a position.
    distance_m = models.PositiveIntegerField(null=True, blank=True)
    lot_distance_m = models.PositiveIntegerField(null=True, blank=True)
    eta_minutes = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=ETA_CHOICES
    )
    rejection_reason_code = models.CharField(
        max_length=20, choices=RejectionReason, blank=True
    )
    rejection_note = models.CharField(max_length=MAX_REJECTION_NOTE, blank=True)
    # Not used in the first version; the product asks cash or card at the car.
    payment_method = models.CharField(max_length=10, choices=PaymentMethod, blank=True)
    placed_at = models.DateTimeField(default=timezone.now)
    accepted_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    not_found_at = models.DateTimeField(null=True, blank=True)
    no_show_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-placed_at",)
        indexes: ClassVar[list[models.Index]] = [
            # The restaurant screen lists a restaurant's orders newest first.
            models.Index(
                fields=["restaurant", "-placed_at"], name="order_restaurant_recent_idx"
            ),
            models.Index(fields=["restaurant", "updated_at"], name="order_changed_idx"),
        ]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["restaurant", "number"],
                name="unique_order_number_per_restaurant",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(customer_lat__isnull=True, customer_lng__isnull=True)
                    | models.Q(customer_lat__isnull=False, customer_lng__isnull=False)
                ),
                name="order_location_complete",
            ),
            # A rejected order has a reason, and only a rejected order does.
            models.CheckConstraint(
                condition=(
                    models.Q(status="rejected") & ~models.Q(rejection_reason_code="")
                )
                | (~models.Q(status="rejected") & models.Q(rejection_reason_code="")),
                name="order_reason_only_when_rejected",
            ),
            # The reason "other" always comes with a note.
            models.CheckConstraint(
                condition=~models.Q(rejection_reason_code="other")
                | ~models.Q(rejection_note=""),
                name="order_other_reason_needs_note",
            ),
        ]

    def __str__(self) -> str:
        return f"#{self.number} {self.restaurant}"

    @property
    def distance_band(self) -> DistanceBand:
        """In the lot, near it, far, or unknown; derived on read, never stored."""
        return distance_band(self.lot_distance_m, self.restaurant.parking_lot.radius_m)

    def clean(self) -> None:
        super().clean()
        self._normalise()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self._normalise()
        super().save(*args, **kwargs)

    def _normalise(self) -> None:
        if self.conversation_id is not None:
            conversation = self.conversation
            align_with_parent(self, conversation, "conversation")
            if self.customer_id is not None and (
                conversation.customer_id != self.customer_id
            ):
                raise ValidationError(
                    {"customer": "This is not the customer of the conversation."}
                )
        if (self.customer_lat is None) != (self.customer_lng is None):
            raise ValidationError(
                {"customer_lat": "Latitude and longitude go together."}
            )


class OrderItem(RestaurantOwnedModel):
    """One line of an order. The names and the price are copies taken when the order was
    placed, so later edits to the menu never change an order that already exists."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    # The line's number in the order, from 1, in the order the customer built it.
    line = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    # A menu item that has been ordered cannot be deleted; it is made unavailable instead.
    menu_item = models.ForeignKey(
        "menu.MenuItem",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order_items",
    )
    name_en = models.CharField(max_length=150)
    name_ar = models.CharField(max_length=150)
    # The item's price plus the price change of every chosen option, in fils.
    unit_price_minor = models.PositiveIntegerField()
    quantity = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(MAX_QUANTITY)]
    )
    # The chosen options as ``{name_en, name_ar, price_delta_minor}``.
    options = models.JSONField(default=list, blank=True)
    note = models.CharField(max_length=200, blank=True)
    line_total_minor = models.PositiveIntegerField()

    class Meta:
        ordering = ("order", "line")
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["order", "line"], name="unique_line_per_order"
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1, quantity__lte=MAX_QUANTITY),
                name="order_item_quantity_in_range",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    line_total_minor=models.F("unit_price_minor") * models.F("quantity")
                ),
                name="order_item_total_is_price_times_quantity",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} x {self.name_en}"

    def clean(self) -> None:
        super().clean()
        self._normalise()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self._normalise()
        super().save(*args, **kwargs)

    def _normalise(self) -> None:
        if self.order_id is not None:
            align_with_parent(self, self.order, "order")
        if not isinstance(self.options, list) or not all(
            isinstance(option, dict) for option in self.options
        ):
            raise ValidationError({"options": "The options must be a list of objects."})


class OrderEvent(RestaurantOwnedModel):
    """One status change of an order, kept as history: who moved it, from where, to where,
    and when (``created_at``). Never edited."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    # Empty for the event that creates the order.
    from_status = models.CharField(max_length=15, choices=OrderStatus, blank=True)
    to_status = models.CharField(max_length=15, choices=OrderStatus)
    actor_type = models.CharField(max_length=10, choices=ActorType)
    # The customer's or the staff member's user id; empty for the system.
    actor_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ("order", "created_at")
        constraints: ClassVar[list[models.BaseConstraint]] = [
            # The system acts on its own; a customer or a staff member is always named.
            models.CheckConstraint(
                condition=(
                    models.Q(actor_type="system", actor_id__isnull=True)
                    | (
                        ~models.Q(actor_type="system")
                        & models.Q(actor_id__isnull=False)
                    )
                ),
                name="order_event_actor_matches_type",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.order}: {self.from_status or '-'} -> {self.to_status}"

    def clean(self) -> None:
        super().clean()
        self._normalise()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self._normalise()
        super().save(*args, **kwargs)

    def _normalise(self) -> None:
        if self.order_id is not None:
            align_with_parent(self, self.order, "order")
