"""The shape of an order for the customer who placed it."""

from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Order, RejectionReason


class BlankAsNullCharField(serializers.CharField):  # type: ignore[misc]
    """A text the database stores as an empty string when it has no value, sent as ``null``."""

    def to_representation(self, value: Any) -> Any:
        return super().to_representation(value) if value else None


REASON_CODES_HELP = (
    "Why the restaurant rejected the order, else null. A list that can grow: treat a code you "
    "do not know as unknown."
)


@extend_schema_field(
    {
        "type": "string",
        "nullable": True,
        "x-extensible-enum": list(RejectionReason.values),
        "description": REASON_CODES_HELP,
    }
)
class RejectionReasonField(BlankAsNullCharField):
    """The rejection reason as an inline nullable string: a named enum with a nullable wrapper
    is read badly by the generated Dart client, so the list is declared in place."""


class OrderSerializer(serializers.ModelSerializer):  # type: ignore[misc]
    eta_minutes = serializers.IntegerField(
        read_only=True,
        allow_null=True,
        help_text="The wait the restaurant gave when it accepted (5, 10 or 15), else null.",
    )
    rejection_reason_code = RejectionReasonField(read_only=True, allow_null=True)
    rejection_note = BlankAsNullCharField(
        read_only=True,
        allow_null=True,
        help_text="The restaurant's note with a rejection (always there for `other`), else null.",
    )

    class Meta:
        model = Order
        fields = (
            "id",
            "number",
            "status",
            "order_type",
            "placed_at",
            "eta_minutes",
            "rejection_reason_code",
            "rejection_note",
            "subtotal_minor",
            "total_minor",
            "currency",
        )
        read_only_fields = fields
