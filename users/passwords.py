"""The strength rules for a new password, answered as a ``400`` with Django's own codes.

Customers (sign-up and password reset) and staff (``POST /auth/password``) use the same rules,
the ones in ``AUTH_PASSWORD_VALIDATORS``.
"""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError
from rest_framework.fields import ErrorDetail

from .models import User


def password_error(error: DjangoValidationError, field: str) -> ValidationError:
    """Django's password messages, with their codes (``password_too_short``...), as a 400."""
    details = [
        ErrorDetail(
            item.message % item.params if item.params else item.message,
            item.code or "invalid",
        )
        for item in error.error_list
    ]
    return ValidationError({field: details})


def check_password_strength(password: str, user: User, field: str) -> None:
    try:
        validate_password(password, user=user)
    except DjangoValidationError as error:
        raise password_error(error, field) from None
