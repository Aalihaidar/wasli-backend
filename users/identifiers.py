"""Normalising and recognising the three sign-in identifiers: username, email and phone.

Every identifier is stored normalised and as ``None`` (NULL) when empty, never as ``""``,
so the unique constraints only apply to values that are actually set.
"""

import re
from typing import Literal

import phonenumbers
from django.core.exceptions import ValidationError

# Phone numbers without a country code are read in this region (the UAE).
DEFAULT_PHONE_REGION = "AE"

# Lowercase after normalisation; the validator accepts any case so "Sara" is
# normalised to "sara" first instead of being rejected.
USERNAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9._-]{2,29}")
# What a typed phone number can contain. A username starts with a letter, so a value that
# only has these characters can never be a username.
_PHONE_CHARACTERS = re.compile(r"[+\d\s().-]+")

IdentifierField = Literal["username", "email", "phone"]


def normalize_username(value: str | None) -> str | None:
    value = (value or "").strip().lower()
    return value or None


def normalize_email(value: str | None) -> str | None:
    value = (value or "").strip().lower()
    return value or None


def normalize_phone(value: str | None) -> str | None:
    """Return the number in international format (``+971501234567``), or ``None`` if blank.

    Raises ``ValidationError`` when the value is not a valid phone number.
    """
    value = (value or "").strip()
    if not value:
        return None
    try:
        number = phonenumbers.parse(value, DEFAULT_PHONE_REGION)
    except phonenumbers.NumberParseException as error:
        raise ValidationError(
            "Enter a valid phone number.", code="invalid_phone"
        ) from error
    if not phonenumbers.is_valid_number(number):
        raise ValidationError("Enter a valid phone number.", code="invalid_phone")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def validate_username(value: str) -> None:
    if not USERNAME_PATTERN.fullmatch(value.strip()):
        raise ValidationError(
            "Use 3 to 30 characters: letters, digits, dots, underscores and hyphens, "
            "starting with a letter.",
            code="invalid_username",
        )


def validate_phone(value: str) -> None:
    normalize_phone(value)


def identify(value: str) -> tuple[IdentifierField, str] | None:
    """Work out which identifier a typed value is and return it normalised.

    Contains ``@`` means email; looks like a phone number and is valid means phone;
    anything else is a username. Returns ``None`` for a value that cannot belong to any
    account (blank, or a phone-looking value that is not a valid number).
    """
    value = value.strip()
    if not value:
        return None
    if "@" in value:
        email = normalize_email(value)
        return ("email", email) if email else None
    if _PHONE_CHARACTERS.fullmatch(value):
        try:
            phone = normalize_phone(value)
        except ValidationError:
            return None
        return ("phone", phone) if phone else None
    username = normalize_username(value)
    return ("username", username) if username else None
