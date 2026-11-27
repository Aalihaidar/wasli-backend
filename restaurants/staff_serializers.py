"""The shapes of the staff sign-in and of ``GET /staff/me``."""

from rest_framework import serializers

from core.permissions import PERMISSION_CHOICES
from restaurants.models import ROLE_CHOICES

from .serializers import (
    SERVICE_RADIUS_HELP,
    OptionalIntegerField,
    arabic_name,
)


class StaffLoginSerializer(serializers.Serializer):  # type: ignore[misc]
    username = serializers.CharField(
        max_length=254,
        help_text="The account's username. An email address or a phone number also works.",
    )
    password = serializers.CharField(
        max_length=128, write_only=True, trim_whitespace=False
    )


class StaffTokenSerializer(serializers.Serializer):  # type: ignore[misc]
    token = serializers.CharField(
        help_text="Send it as `Authorization: Token <token>` on every staff call."
    )


class StaffPasswordSerializer(serializers.Serializer):  # type: ignore[misc]
    current_password = serializers.CharField(
        max_length=128, write_only=True, trim_whitespace=False
    )
    new_password = serializers.CharField(
        max_length=128, write_only=True, trim_whitespace=False
    )


class StaffRestaurantSerializer(serializers.Serializer):  # type: ignore[misc]
    slug = serializers.CharField()
    name_en = serializers.CharField()
    name_ar = arabic_name(read_only=False)
    logo_url = serializers.ImageField(source="logo", read_only=True, allow_null=True)
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    service_radius_m = OptionalIntegerField(
        required=False, help_text=SERVICE_RADIUS_HELP
    )
    currency = serializers.CharField()


class StaffMeSerializer(serializers.Serializer):  # type: ignore[misc]
    id = serializers.UUIDField()
    username = serializers.CharField()
    full_name = serializers.CharField()
    role = serializers.ChoiceField(
        choices=ROLE_CHOICES,
        help_text="The member's role at this restaurant. A list that can grow.",
    )
    permissions = serializers.ListField(
        child=serializers.ChoiceField(choices=PERMISSION_CHOICES),
        help_text=(
            "What the member may do. Hide an action the list does not allow; the server "
            "stays the authority."
        ),
    )
    must_change_password = serializers.BooleanField(
        help_text=(
            "True for a new member with a temporary password: ask for a new one with "
            "`POST /auth/password`."
        ),
    )
    # No help_text and not read-only: either would wrap the reference in `allOf`, which the
    # generated clients read badly (docs/api-conventions.md).
    restaurant = StaffRestaurantSerializer()
