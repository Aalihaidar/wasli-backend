"""The shape of an order for the customer who placed it."""

from typing import Any

from rest_framework import serializers

from .models import Order


class BlankAsNullCharField(serializers.CharField):  # type: ignore[misc]
    """A text the database stores as an empty string when it has no value, sent as ``null``."""

    def to_representation(self, value: Any) -> Any:
        return super().to_representation(value) if value else None


class OrderSerializer(serializers.ModelSerializer):  # type: ignore[misc]
    eta_minutes = serializers.IntegerField(
        read_only=True,
        allow_null=True,
        help_text="The wait the restaurant gave when it accepted (5, 10 or 15), else null.",
    )
    rejection_reason_code = BlankAsNullCharField(
        read_only=True,
        allow_null=True,
        help_text=(
            "Why the restaurant rejected the order: `item_unavailable`, `too_busy`, "
            "`closing_soon`, `too_far`, `location_unclear` or `other`; null otherwise."
        ),
    )
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
