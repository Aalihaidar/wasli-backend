"""Staff sign-in, sign-out and password change (``/auth/login``, ``/auth/logout``,
``/auth/password``).

A staff token is DRF's ``authtoken`` token: one per account, shared by every device of that
account until per-device tokens are built (before the pilot). A token is only ever issued to
an active member of an active restaurant, so a customer or a platform account that signs in
here gets the same answer as a wrong password and no token row is created for them.
"""

from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.fields import ErrorDetail

from core import limits
from users.models import User
from users.passwords import check_password_strength

from .services import resolve_membership

# Wrong tries per username in a window, whatever the address (the per-address limit is the
# ``staff_login`` throttle scope). A success clears the count.
LOGIN_FAILURES = 10
LOGIN_WINDOW_SECONDS = 15 * 60


class InvalidStaffCredentials(APIException):  # type: ignore[misc]
    """A wrong username or password, an inactive account, or an account that is not an active
    member of a restaurant: one answer for all of them, so the endpoint never says which
    accounts exist. A plain 401: ``AuthenticationFailed`` would be turned into a 403 on a view
    that has no token scheme to challenge with."""

    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "authentication_failed"
    default_detail = "The username or the password is not correct."


def log_in(*, identifier: str, password: str) -> str:
    """The staff token of an active member who gave the right username and password."""
    key = f"staff-login:{limits.digest(identifier.strip().lower())}"
    limits.hit(key, limit=LOGIN_FAILURES, window_seconds=LOGIN_WINDOW_SECONDS)
    user = authenticate(username=identifier, password=password)
    if not isinstance(user, User) or resolve_membership(user) is None:
        raise InvalidStaffCredentials
    limits.clear(key)
    token, _ = Token.objects.get_or_create(user=user)
    update_last_login(type(user), user)
    return str(token.key)


def log_out(token: Token) -> None:
    """End the token. Because the token belongs to the account, every device is signed out."""
    token.delete()


def change_password(*, user: User, current_password: str, new_password: str) -> None:
    """Replace the password and clear ``must_change_password``. The token stays valid."""
    if not user.check_password(current_password):
        raise ValidationError(
            {
                "current_password": [
                    ErrorDetail(
                        "The current password is not correct.", "password_incorrect"
                    )
                ]
            }
        )
    if new_password == current_password:
        raise ValidationError(
            {
                "new_password": [
                    ErrorDetail(
                        "The new password must differ from the current one.",
                        "password_unchanged",
                    )
                ]
            }
        )
    check_password_strength(new_password, user, "new_password")
    user.set_password(new_password)
    user.must_change_password = False
    user.save(update_fields=["password", "must_change_password", "updated_at"])
