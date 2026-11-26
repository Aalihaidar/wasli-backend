"""The customer-account endpoints (``/api/v1/customers/...``).

Sign-up, verification, sign-in and password reset are public; ``logout``, ``me`` and the
contact calls need ``Authorization: Customer <token>``. Every one is throttled, and the flows
themselves are in ``customers.accounts``.
"""

from typing import Any

from drf_spectacular.utils import OpenApiExample, extend_schema
from drf_standardized_errors.openapi_serializers import ErrorResponse401Serializer
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from config.api_errors import Error403ResponseSerializer
from core.views import PublicAPIView

from . import accounts
from .authentication import CustomerTokenAuthentication
from .permissions import IsCustomer, get_customer
from .serializers import (
    ContactSerializer,
    ContactVerifySerializer,
    CustomerProfileSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetSentSerializer,
    PasswordResetSerializer,
    ResendSerializer,
    SentCodeSerializer,
    SessionSerializer,
    SignupSerializer,
    VerifySerializer,
)
from .services import revoke_session

TAGS = ["customers"]


def _contact(identifier: str) -> tuple[str, str]:
    """The kind and value of an identifier the serializer already checked."""
    found = accounts.contact_of(identifier)
    assert found is not None  # noqa: S101
    return found


def _user_agent(request: Request) -> str:
    return str(request.headers.get("user-agent", ""))[:255]


class PublicCustomerView(PublicAPIView):
    """A public view with its own throttle scope (``throttle_scope`` on the subclass)."""

    throttle_classes = [ScopedRateThrottle]  # noqa: RUF012


class CustomerView(APIView):  # type: ignore[misc]
    """A view that needs a customer token. The default per-user throttle applies."""

    authentication_classes = [CustomerTokenAuthentication]  # noqa: RUF012
    permission_classes = [IsCustomer]  # noqa: RUF012


class SignupView(PublicCustomerView):
    throttle_scope = "customer_signup"

    @extend_schema(
        operation_id="customers_signup",
        tags=TAGS,
        summary="Sign up",
        description=(
            "Creates an unverified account from a name, **an email or a phone number**, a password "
            "and a language, and sends a six-digit code to that contact. The customer then calls "
            "`customers_verify`. Signing up again with a contact whose account is still unverified "
            "restarts the sign-up (new name, password and code); a contact of a verified account is "
            "`409 account_exists`. No token is needed."
        ),
        request=SignupSerializer,
        responses={201: SentCodeSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sent = accounts.sign_up(**serializer.validated_data)
        return Response(SentCodeSerializer(sent).data, status=status.HTTP_201_CREATED)


class VerifyView(PublicCustomerView):
    throttle_scope = "customer_verify"

    @extend_schema(
        operation_id="customers_verify",
        tags=TAGS,
        summary="Verify the sign-up code",
        description=(
            "Checks the code sent at sign-up (valid 10 minutes, 5 wrong attempts). On success the "
            "contact is verified and the customer token is returned, **only here and at sign-in**. "
            "An unknown contact gets `code_invalid`, so the call reveals nothing."
        ),
        request=VerifySerializer,
        responses={200: SessionSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = VerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        kind, value = _contact(serializer.validated_data["identifier"])
        customer, token = accounts.verify_signup(
            kind=kind,
            value=value,
            code=serializer.validated_data["code"],
            user_agent=_user_agent(request),
        )
        body = SessionSerializer({"token": token, "customer": customer})
        return Response(body.data)


class ResendCodeView(PublicCustomerView):
    throttle_scope = "customer_resend"

    @extend_schema(
        operation_id="customers_resend_code",
        tags=TAGS,
        summary="Send a new sign-up code",
        description=(
            "Sends a new code to an unverified account. A new code replaces the old one, comes at "
            "most every 60 seconds and at most 5 an hour per contact (`429 throttled` with "
            "`Retry-After`). A contact with no account, or an account already verified, gets the "
            "same `202` and nothing is sent."
        ),
        request=ResendSerializer,
        responses={202: SentCodeSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = ResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        kind, value = _contact(serializer.validated_data["identifier"])
        sent = accounts.resend_code(kind=kind, value=value)
        return Response(SentCodeSerializer(sent).data, status=status.HTTP_202_ACCEPTED)


class LoginView(PublicCustomerView):
    throttle_scope = "customer_login"

    @extend_schema(
        operation_id="customers_login",
        tags=TAGS,
        summary="Sign in",
        description=(
            "Signs a customer in with an email address or a phone number and the password, and "
            "returns the customer token. A wrong password and a contact with no account are the "
            "same `401 authentication_failed`, so the answer never says whether an account exists. "
            "Only a caller who gives the right password learns more: `403 account_not_verified` "
            "until the sign-up code is verified (the app opens the code screen), and `403 "
            "permission_denied` for a blocked or deactivated account. A missing or blank "
            "`identifier` or `password` is a `400` that names the field in `attr`. Ten tries per "
            "contact in 15 minutes (`429 throttled`)."
        ),
        request=LoginSerializer,
        responses={
            200: SessionSerializer,
            401: ErrorResponse401Serializer,
            403: Error403ResponseSerializer,
        },
        examples=[
            OpenApiExample(
                "WrongPasswordOrUnknownContact",
                value={
                    "type": "client_error",
                    "errors": [
                        {
                            "code": "authentication_failed",
                            "detail": "The contact or the password is not correct.",
                            "attr": None,
                        }
                    ],
                },
                response_only=True,
                status_codes=["401"],
            ),
            OpenApiExample(
                "AccountNotVerified",
                value={
                    "type": "client_error",
                    "errors": [
                        {
                            "code": "account_not_verified",
                            "detail": "Verify the code sent to your contact before signing in.",
                            "attr": None,
                        }
                    ],
                },
                response_only=True,
                status_codes=["403"],
            ),
            OpenApiExample(
                "BlockedOrDeactivated",
                value={
                    "type": "client_error",
                    "errors": [
                        {
                            "code": "permission_denied",
                            "detail": "You do not have permission to perform this action.",
                            "attr": None,
                        }
                    ],
                },
                response_only=True,
                status_codes=["403"],
            ),
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer, token = accounts.log_in(
            identifier=serializer.validated_data["identifier"],
            password=serializer.validated_data["password"],
            user_agent=_user_agent(request),
        )
        return Response(SessionSerializer({"token": token, "customer": customer}).data)


class LogoutView(CustomerView):
    @extend_schema(
        operation_id="customers_logout",
        tags=TAGS,
        summary="Sign out",
        description="Revokes the token of this device. Other devices stay signed in.",
        request=None,
        responses={204: None},
    )
    def post(self, request: Request) -> Response:
        revoke_session(request.auth)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(CustomerView):
    @extend_schema(
        operation_id="customers_me",
        tags=TAGS,
        summary="Read the profile",
        description="The customer's name, language and contacts, and whether each contact is verified.",
        responses={200: CustomerProfileSerializer},
    )
    def get(self, request: Request) -> Response:
        return Response(CustomerProfileSerializer(get_customer(request)).data)


class ContactView(CustomerView):
    throttle_classes = [ScopedRateThrottle]  # noqa: RUF012
    throttle_scope = "customer_contact"

    @extend_schema(
        operation_id="customers_contact_add",
        tags=TAGS,
        summary="Add the missing contact",
        description=(
            "Sends a code to the contact the account does not have yet: an email for a phone "
            "sign-up, a phone number for an email sign-up. It is saved only after "
            "`customers_contact_verify`. Changing a contact the account already has is not offered "
            "(`409 contact_already_set`); a contact that belongs to another account is "
            "`409 account_exists`."
        ),
        request=ContactSerializer,
        responses={202: SentCodeSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = ContactSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sent = accounts.add_contact(
            customer=get_customer(request), **serializer.validated_data
        )
        return Response(SentCodeSerializer(sent).data, status=status.HTTP_202_ACCEPTED)


class ContactVerifyView(CustomerView):
    throttle_classes = [ScopedRateThrottle]  # noqa: RUF012
    throttle_scope = "customer_verify"

    @extend_schema(
        operation_id="customers_contact_verify",
        tags=TAGS,
        summary="Confirm the added contact",
        description=(
            "Checks the code sent to the contact added with `customers_contact_add`, saves the "
            "contact as verified and returns the profile. `409 no_pending_contact` when none waits."
        ),
        request=ContactVerifySerializer,
        responses={200: CustomerProfileSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = ContactVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = accounts.verify_contact(
            customer=get_customer(request), code=serializer.validated_data["code"]
        )
        return Response(CustomerProfileSerializer(customer).data)


class PasswordResetView(PublicCustomerView):
    throttle_scope = "customer_reset"

    @extend_schema(
        operation_id="customers_password_reset",
        tags=TAGS,
        summary="Ask for a password reset code",
        description=(
            "Sends a six-digit code to the customer's **verified** contact. The answer is the same "
            "`202` whether or not an account exists, and the limits (one a minute, five an hour per "
            "contact) are the same too."
        ),
        request=PasswordResetSerializer,
        responses={202: PasswordResetSentSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        kind, value = _contact(serializer.validated_data["identifier"])
        accounts.request_password_reset(kind=kind, value=value)
        body = PasswordResetSentSerializer(
            {"code_expires_in_seconds": accounts.CODE_EXPIRES_IN}
        )
        return Response(body.data, status=status.HTTP_202_ACCEPTED)


class PasswordResetConfirmView(PublicCustomerView):
    throttle_scope = "customer_reset_confirm"

    @extend_schema(
        operation_id="customers_password_reset_confirm",
        tags=TAGS,
        summary="Set a new password with the code",
        description=(
            "Checks the reset code and sets the new password. Every token of the customer is "
            "revoked, so every device signs in again. A password that is too weak is a `400` and "
            "does not spend the code."
        ),
        request=PasswordResetConfirmSerializer,
        responses={204: None},
    )
    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data: dict[str, Any] = serializer.validated_data
        kind, value = _contact(data["identifier"])
        accounts.confirm_password_reset(
            kind=kind, value=value, code=data["code"], new_password=data["new_password"]
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
