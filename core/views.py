from typing import ClassVar

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from assistant.availability import ai_enabled

from .locales import Locale

# How often the sites poll the messages and the orders, in seconds (docs: Polling).
POLL_INTERVAL_SECONDS = 3


class PublicAPIView(APIView):  # type: ignore[misc]
    """A view anybody may call: no token is read (a stale one never causes a 401) and nothing
    is required. The default throttles still apply."""

    authentication_classes: ClassVar[list[type]] = []
    permission_classes: ClassVar[list[type]] = [AllowAny]


class ConfigSerializer(serializers.Serializer):  # type: ignore[misc]
    location_check = serializers.ChoiceField(
        choices=["off", "warn", "enforce"],
        help_text=(
            "How an order's location is checked: `off`, `warn` (recorded, never "
            "blocks) or `enforce`."
        ),
    )
    require_screen_online = serializers.BooleanField(
        help_text="True: a restaurant is listed only while its site is online."
    )
    ai_enabled = serializers.BooleanField(
        help_text="False when the assistant is not available: use the item picker."
    )
    languages = serializers.ListField(
        child=serializers.ChoiceField(choices=[locale.value for locale in Locale]),
        help_text="The languages of the product.",
    )
    poll_interval_seconds = serializers.IntegerField(
        help_text="How often the sites poll for new messages and orders."
    )


class ConfigView(PublicAPIView):
    @extend_schema(
        operation_id="config_retrieve",
        tags=["config"],
        summary="Read the public configuration",
        description=(
            "The switches the apps need before anything else: the location rule, whether "
            "a restaurant must be online to be listed, whether the assistant is available, "
            "the languages and the polling interval. No token is needed."
        ),
        responses={200: ConfigSerializer},
    )
    def get(self, request: Request) -> Response:
        return Response(
            ConfigSerializer(
                {
                    "location_check": settings.LOCATION_CHECK,
                    "require_screen_online": settings.REQUIRE_SCREEN_ONLINE,
                    "ai_enabled": ai_enabled(),
                    "languages": [locale.value for locale in Locale],
                    "poll_interval_seconds": POLL_INTERVAL_SECONDS,
                }
            ).data
        )
