"""The errors of the customer-account endpoints, each with the stable ``code`` the apps branch on.

Every one of them is rendered by the shared error body (``{"type", "errors": [{"code",
"detail", "attr"}]}``). ``detail`` is for people, ``code`` is for programs.
"""

from rest_framework import status
from rest_framework.exceptions import APIException


class _Coded(APIException):  # type: ignore[misc]
    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail=detail or self.default_detail, code=self.default_code)


class CodeInvalid(_Coded):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "code_invalid"
    default_detail = "The code is not correct."


class CodeExpired(_Coded):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "code_expired"
    default_detail = "The code has expired. Ask for a new one."


class TooManyAttempts(_Coded):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "too_many_attempts"
    default_detail = "Too many wrong attempts. Ask for a new code."


class InvalidCredentials(_Coded):
    """A wrong contact or password. It is a plain 401: this view has no token scheme to
    challenge with, so DRF's ``AuthenticationFailed`` would have been turned into a 403."""

    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "authentication_failed"
    default_detail = "The contact or the password is not correct."


class AccountNotVerified(_Coded):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "account_not_verified"
    default_detail = "Verify the code sent to your contact before signing in."


class AccountExists(_Coded):
    status_code = status.HTTP_409_CONFLICT
    default_code = "account_exists"
    default_detail = "An account already uses this contact."


class ContactAlreadySet(_Coded):
    status_code = status.HTTP_409_CONFLICT
    default_code = "contact_already_set"
    default_detail = "This account already has this kind of contact."


class NoPendingContact(_Coded):
    status_code = status.HTTP_409_CONFLICT
    default_code = "no_pending_contact"
    default_detail = "There is no contact waiting for a code."
