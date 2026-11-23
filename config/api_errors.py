"""The one error body of the API, as documented in the OpenAPI contract.

drf-standardized-errors produces the bodies at runtime; DRF_STANDARDIZED_ERRORS["ERROR_SCHEMAS"]
points here so every operation shares ONE 400 schema instead of a generated one per endpoint and
field. ``attr`` is the field the error belongs to (dotted for nested data) or null.
"""

from django.db import models
from drf_standardized_errors.openapi_serializers import (
    ClientErrorEnum,
    ValidationErrorEnum,
)
from rest_framework import serializers


class Error400Serializer(serializers.Serializer):  # type: ignore[misc]
    code = serializers.CharField()
    detail = serializers.CharField()
    attr = serializers.CharField(allow_null=True)


class Error400ResponseSerializer(serializers.Serializer):  # type: ignore[misc]
    """``validation_error``: invalid input. ``client_error``: an unreadable request body."""

    type = serializers.ChoiceField(
        choices=[*ValidationErrorEnum.choices, *ClientErrorEnum.choices]
    )
    errors = Error400Serializer(many=True)


class ErrorCode409Enum(models.TextChoices):
    """Stable codes of a ``409`` conflict. A new conflict code is added here and nowhere else."""

    ORDER_INVALID_TRANSITION = "order_invalid_transition"
    ACCOUNT_EXISTS = "account_exists"
    CONTACT_ALREADY_SET = "contact_already_set"
    NO_PENDING_CONTACT = "no_pending_contact"
    INVALID_ACTION_FOR_STATE = "invalid_action_for_state"
    CONVERSATION_EXPIRED = "conversation_expired"


class Error409Serializer(serializers.Serializer):  # type: ignore[misc]
    code = serializers.ChoiceField(choices=ErrorCode409Enum.choices)
    detail = serializers.CharField()
    attr = serializers.CharField(allow_null=True)


class Error409ResponseSerializer(serializers.Serializer):  # type: ignore[misc]
    """``409``: the request is valid but conflicts with the current state."""

    type = serializers.ChoiceField(choices=ClientErrorEnum.choices)
    errors = Error409Serializer(many=True)


class ErrorCode403Enum(models.TextChoices):
    """Stable codes of a ``403``."""

    PERMISSION_DENIED = "permission_denied"
    ACCOUNT_NOT_VERIFIED = "account_not_verified"
    PHONE_NOT_VERIFIED = "phone_not_verified"


class Error403Serializer(serializers.Serializer):  # type: ignore[misc]
    code = serializers.ChoiceField(choices=ErrorCode403Enum.choices)
    detail = serializers.CharField()
    attr = serializers.CharField(allow_null=True)


class Error403ResponseSerializer(serializers.Serializer):  # type: ignore[misc]
    """``403``: not allowed for this caller or in this state."""

    type = serializers.ChoiceField(choices=ClientErrorEnum.choices)
    errors = Error403Serializer(many=True)


class ErrorCode429Enum(models.TextChoices):
    """Stable codes of a ``429``."""

    THROTTLED = "throttled"
    TOO_MANY_ATTEMPTS = "too_many_attempts"


class Error429Serializer(serializers.Serializer):  # type: ignore[misc]
    code = serializers.ChoiceField(choices=ErrorCode429Enum.choices)
    detail = serializers.CharField()
    attr = serializers.CharField(allow_null=True)


class Error429ResponseSerializer(serializers.Serializer):  # type: ignore[misc]
    """``429``: too many requests, or too many wrong attempts at a code."""

    type = serializers.ChoiceField(choices=ClientErrorEnum.choices)
    errors = Error429Serializer(many=True)
