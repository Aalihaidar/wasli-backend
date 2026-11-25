"""The request and response shapes of the customer-account endpoints."""

from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from core.locales import Locale
from messaging.models import Channel
from users.identifiers import normalize_email, normalize_phone
from users.models import User
from users.passwords import check_password_strength

from .accounts import CODE_EXPIRES_IN, RESEND_IN, contact_of
from .models import Customer

# Plain English labels, so the contract carries no Arabic script (the model's own choices do).
LOCALES = [(Locale.EN.value, "English"), (Locale.AR.value, "Arabic")]


class ContactIdentifierField(serializers.CharField):  # type: ignore[misc]
    """An email address or a phone number, in any form a person types it, returned normalised
    (lower-case email, international phone). A username is not a contact."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("max_length", 254)
        kwargs.setdefault(
            "help_text",
            "The email address or the phone number, as the customer typed it.",
        )
        super().__init__(**kwargs)

    def to_internal_value(self, data: Any) -> str:
        value: str = super().to_internal_value(data)
        found = contact_of(value)
        if found is None:
            raise serializers.ValidationError(
                "Enter an email address or a phone number.", code="invalid"
            )
        return found[1]


class CodeField(serializers.RegexField):  # type: ignore[misc]
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            r"^\d{6}$",
            max_length=6,
            help_text="The six-digit code.",
            error_messages={"invalid": "Enter the six-digit code."},
            **kwargs,
        )


class PasswordField(serializers.CharField):  # type: ignore[misc]
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            write_only=True,
            max_length=128,
            trim_whitespace=False,
            style={"input_type": "password"},
            **kwargs,
        )


def _contact_from(attrs: dict[str, Any]) -> tuple[str, str]:
    """Exactly one of ``email`` and ``phone``, normalised."""
    email, phone = attrs.get("email"), attrs.get("phone")
    if bool(email) == bool(phone):
        raise serializers.ValidationError(
            {
                "email": "Give an email address or a phone number, not both and not neither."
            },
            code="contact_required",
        )
    if email:
        return "email", normalize_email(email) or ""
    try:
        normalized = normalize_phone(phone)
    except DjangoValidationError:
        raise serializers.ValidationError(
            {"phone": "Enter a valid phone number."}, code="invalid"
        ) from None
    return "phone", normalized or ""


class SignupSerializer(serializers.Serializer):  # type: ignore[misc]
    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField(
        required=False, max_length=254, help_text="Give this or phone."
    )
    phone = serializers.CharField(
        required=False, max_length=32, help_text="Give this or email."
    )
    password = PasswordField()
    locale = serializers.ChoiceField(
        choices=LOCALES,
        help_text="The customer's language; the code message is written in it.",
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        kind, value = _contact_from(attrs)
        probe = User(**{kind: value}, full_name=attrs["full_name"])
        check_password_strength(attrs["password"], probe, "password")
        return {
            "full_name": attrs["full_name"],
            "kind": kind,
            "value": value,
            "password": attrs["password"],
            "locale": attrs["locale"],
        }


class VerifySerializer(serializers.Serializer):  # type: ignore[misc]
    identifier = ContactIdentifierField()
    code = CodeField()


class ResendSerializer(serializers.Serializer):  # type: ignore[misc]
    identifier = ContactIdentifierField()


class LoginSerializer(serializers.Serializer):  # type: ignore[misc]
    identifier = serializers.CharField(
        max_length=254, help_text="The email address or the phone number."
    )
    password = PasswordField()


class ContactSerializer(serializers.Serializer):  # type: ignore[misc]
    email = serializers.EmailField(
        required=False, max_length=254, help_text="Give this or phone."
    )
    phone = serializers.CharField(
        required=False, max_length=32, help_text="Give this or email."
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        kind, value = _contact_from(attrs)
        return {"kind": kind, "value": value}


class ContactVerifySerializer(serializers.Serializer):  # type: ignore[misc]
    code = CodeField()


class PasswordResetSerializer(serializers.Serializer):  # type: ignore[misc]
    identifier = ContactIdentifierField()


class PasswordResetConfirmSerializer(serializers.Serializer):  # type: ignore[misc]
    identifier = ContactIdentifierField()
    code = CodeField()
    new_password = PasswordField()


# --- responses -------------------------------------------------------------------------------


class SentCodeSerializer(serializers.Serializer):  # type: ignore[misc]
    identifier = serializers.CharField(
        help_text="The contact the code was sent to, normalised."
    )
    channel = serializers.ChoiceField(choices=Channel.choices)
    code_expires_in_seconds = serializers.IntegerField(default=CODE_EXPIRES_IN)
    resend_available_in_seconds = serializers.IntegerField(default=RESEND_IN)


class PasswordResetSentSerializer(serializers.Serializer):  # type: ignore[misc]
    code_expires_in_seconds = serializers.IntegerField()


class CustomerProfileSerializer(serializers.ModelSerializer):  # type: ignore[misc]
    full_name = serializers.CharField(source="display_name", read_only=True)
    locale = serializers.ChoiceField(choices=LOCALES, read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True, allow_null=True)
    phone = serializers.CharField(source="user.phone", read_only=True, allow_null=True)
    email_verified = serializers.SerializerMethodField()
    phone_verified = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = (
            "id",
            "full_name",
            "locale",
            "email",
            "email_verified",
            "phone",
            "phone_verified",
        )
        read_only_fields = fields

    def get_email_verified(self, customer: Customer) -> bool:
        return customer.user.email_verified_at is not None

    def get_phone_verified(self, customer: Customer) -> bool:
        return customer.user.phone_verified_at is not None


class SessionSerializer(serializers.Serializer):  # type: ignore[misc]
    token = serializers.CharField(
        help_text="Sent as `Authorization: Customer <token>`. Shown only here and at sign-in."
    )
    customer = CustomerProfileSerializer()
