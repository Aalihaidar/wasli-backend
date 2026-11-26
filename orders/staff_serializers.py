"""The shape of an order for the restaurant's staff (``StaffOrder``) and of the polling list.

One schema serves the list, accept, reject and the later Ready step. The optional properties are
absent, never ``null`` (``vehicle`` and ``parking_note`` belong to a car order, ``customer_location``
exists only when the customer shared a position); the nullable scalars are the ones that are empty
until the restaurant answers. No customer name, email or phone is ever returned.
"""

from typing import Any

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from core.geo import DISTANCE_BAND_CHOICES, LocationSource
from core.order_types import OrderType

from .models import MAX_REJECTION_NOTE, Order, OrderStatus, RejectionReason
from .serializers import BlankAsNullCharField, RejectionReasonField


@extend_schema_field(
    {
        "type": "string",
        "x-extensible-enum": [source.value for source in LocationSource],
        "description": (
            "`gps`, or `simulated` for the test button on staging. A list that can grow: "
            "treat a value you do not know as unknown."
        ),
    }
)
class LocationSourceField(serializers.CharField):  # type: ignore[misc]
    """Declared in place, not as a named enum: the customer's position request has its own
    closed list under the same property name, and a shared name would merge the two."""


class StaffOrderOptionSerializer(serializers.Serializer):  # type: ignore[misc]
    name_en = serializers.CharField()
    name_ar = serializers.CharField()
    price_delta_minor = serializers.IntegerField(
        help_text="The change to the item's price, in fils."
    )


class StaffOrderItemSerializer(serializers.Serializer):  # type: ignore[misc]
    line = serializers.IntegerField(help_text="The line's number in the order, from 1.")
    name_en = serializers.CharField()
    name_ar = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_price_minor = serializers.IntegerField(
        help_text="The item's price with its options, in fils."
    )
    options = StaffOrderOptionSerializer(many=True)
    note = serializers.CharField(help_text="The customer's note on the line, or empty.")
    line_total_minor = serializers.IntegerField()


class StaffVehicleSerializer(serializers.Serializer):  # type: ignore[misc]
    plate = serializers.CharField(source="vehicle_plate")
    model = serializers.CharField(source="vehicle_model")
    colour = serializers.CharField(source="vehicle_colour")


class StaffLocationSerializer(serializers.Serializer):  # type: ignore[misc]
    lat = serializers.FloatField(source="customer_lat")
    lng = serializers.FloatField(source="customer_lng")
    accuracy_m = serializers.FloatField(
        source="location_accuracy_m",
        allow_null=True,
        help_text="How accurate the position is, in metres, when the phone said.",
    )
    source = LocationSourceField(source="location_source")
    captured_at = serializers.DateTimeField(
        source="location_captured_at", allow_null=True
    )


class StaffOrderSerializer(serializers.Serializer):  # type: ignore[misc]
    id = serializers.UUIDField()
    number = serializers.IntegerField(help_text="The restaurant's own order number.")
    status = serializers.ChoiceField(choices=OrderStatus.choices)
    order_type = serializers.ChoiceField(choices=OrderType.choices)
    placed_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField(
        help_text=(
            "Moves on every change to the order. Merge by `id` and keep the latest: an order "
            "can arrive again unchanged, with the same value."
        )
    )
    decided_at = serializers.DateTimeField(
        allow_null=True,
        help_text="When the order was accepted or rejected; null while it is placed.",
    )
    eta_minutes = serializers.IntegerField(
        allow_null=True,
        help_text="The wait the restaurant gave when it accepted (5, 10 or 15), else null.",
    )
    rejection_reason_code = RejectionReasonField(allow_null=True)
    rejection_note = BlankAsNullCharField(
        allow_null=True,
        help_text="The restaurant's note with a rejection (always there for `other`), else null.",
    )
    items = StaffOrderItemSerializer(many=True)
    customer_note = serializers.CharField(
        help_text="The customer's note for the whole order, or empty."
    )
    subtotal_minor = serializers.IntegerField()
    total_minor = serializers.IntegerField()
    currency = serializers.CharField()
    # The three below are optional properties, absent when they do not apply. No help_text and
    # not read-only on the nested ones: either would wrap the reference in `allOf`.
    vehicle = StaffVehicleSerializer(source="*", required=False)
    parking_note = serializers.CharField(
        required=False,
        help_text="Where the car is, as the customer said it. Present for a car order.",
    )
    customer_location = StaffLocationSerializer(source="*", required=False)
    distance_m = serializers.IntegerField(
        allow_null=True,
        help_text="Metres from the customer to the restaurant; null without a position.",
    )
    distance_band = serializers.ChoiceField(
        choices=DISTANCE_BAND_CHOICES,
        help_text=(
            "`in_lot` within the restaurant's service distance, `near`, `far`, or `unknown` "
            "without a position. A list that can grow."
        ),
    )

    def to_representation(self, instance: Order) -> dict[str, Any]:
        data: dict[str, Any] = super().to_representation(instance)
        if instance.order_type != OrderType.CAR:
            data.pop("vehicle", None)
            data.pop("parking_note", None)
        if instance.customer_lat is None or instance.customer_lng is None:
            data.pop("customer_location", None)
        return data


class SinceField(serializers.DateTimeField):  # type: ignore[misc]
    """A timestamp that is not in the future. Both a value that is not a timestamp and a time
    that has not come yet are ``invalid_since``: the app only ever sends back a ``server_time``."""

    default_error_messages = {  # noqa: RUF012
        "invalid_since": (
            "Use the server_time of the last answer: a timestamp such as "
            "2026-12-01T10:15:00Z that is not in the future."
        )
    }

    def to_internal_value(self, value: Any) -> Any:
        try:
            parsed = super().to_internal_value(value)
        except serializers.ValidationError:
            self.fail("invalid_since")
        if parsed > timezone.now():
            self.fail("invalid_since")
        return parsed


class StaffOrdersQuerySerializer(serializers.Serializer):  # type: ignore[misc]
    since = SinceField(
        required=False,
        help_text=(
            "The `server_time` of the previous answer. Without it, the orders created or "
            "changed in the last 24 hours."
        ),
    )


class StaffOrderListSerializer(serializers.Serializer):  # type: ignore[misc]
    server_time = serializers.DateTimeField(
        help_text="Send it back as `since` on the next call."
    )
    orders = StaffOrderSerializer(many=True)


class StaffAcceptSerializer(serializers.Serializer):  # type: ignore[misc]
    eta_minutes = serializers.IntegerField(
        help_text="The wait the restaurant promises, in minutes: 5, 10 or 15."
    )


@extend_schema_field(
    {
        "type": "string",
        "x-extensible-enum": list(RejectionReason.values),
        "description": (
            "Why the restaurant rejects the order: `item_unavailable`, `too_busy`, "
            "`closing_soon`, `too_far`, `location_unclear` or `other`."
        ),
    }
)
class RejectionReasonInput(serializers.CharField):  # type: ignore[misc]
    """The reason in a request, declared in place like the one in the answer."""


class StaffRejectSerializer(serializers.Serializer):  # type: ignore[misc]
    reason_code = RejectionReasonInput()
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=MAX_REJECTION_NOTE,
        help_text=(
            f"A note for the customer, at most {MAX_REJECTION_NOTE} characters. Required "
            "when the reason is `other`."
        ),
    )
