"""The staff sign-in endpoints and the member's own profile.

``login`` is public (a stale token is never read); everything else needs
``Authorization: Token <token>`` and an active membership. The order endpoints come in the
next slices (``docs/steps.md``, D3).
"""

from typing import Any, ClassVar

from drf_spectacular.utils import extend_schema
from drf_standardized_errors.openapi_serializers import ErrorResponse401Serializer
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.permissions import permissions_for_role
from core.views import PublicAPIView

from . import staff_auth
from .permissions import IsStaffMember, get_membership
from .staff_serializers import (
    StaffLoginSerializer,
    StaffMeSerializer,
    StaffPasswordSerializer,
    StaffTokenSerializer,
)

AUTH_TAGS = ["auth"]
STAFF_TAGS = ["staff"]


class StaffLoginView(PublicAPIView):
    throttle_classes: ClassVar[list[type]] = [ScopedRateThrottle]
    throttle_scope = "staff_login"

    @extend_schema(
        operation_id="staff_login",
        tags=AUTH_TAGS,
        summary="Sign a staff member in",
        description=(
            "Signs in a member of a restaurant with the account's username (an email address "
            "or a phone number also works) and the password, and returns the staff token. "
            "A wrong username or password, an inactive account and an account that is not an "
            "active member of a restaurant (a customer, the platform team) are all the same "
            "`401 authentication_failed`, and no token is created for them. The token belongs "
            "to the account, not to the device: signing in again returns the same token and "
            "signing out ends it everywhere. Ten tries a minute per address and ten wrong "
            "tries per username in 15 minutes."
        ),
        request=StaffLoginSerializer,
        responses={200: StaffTokenSerializer, 401: ErrorResponse401Serializer},
    )
    def post(self, request: Request) -> Response:
        serializer = StaffLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = staff_auth.log_in(
            identifier=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        return Response(StaffTokenSerializer({"token": token}).data)


class StaffAPIView(APIView):  # type: ignore[misc]
    """A view for a signed-in member: the default ``Token`` authentication, then the
    membership check. The default per-account throttle applies."""

    permission_classes: ClassVar[list[type]] = [IsAuthenticated, IsStaffMember]


class StaffLogoutView(APIView):  # type: ignore[misc]
    """Any valid token can sign out, even one whose account lost its membership: the member
    is never stuck signed in."""

    @extend_schema(
        operation_id="staff_logout",
        tags=AUTH_TAGS,
        summary="Sign a staff member out",
        description=(
            "Deletes the staff token. Because the token belongs to the account, every device "
            "of that account is signed out."
        ),
        request=None,
        responses={204: None},
    )
    def post(self, request: Request) -> Response:
        assert isinstance(request.auth, Token)  # noqa: S101
        staff_auth.log_out(request.auth)
        return Response(status=status.HTTP_204_NO_CONTENT)


class StaffPasswordView(StaffAPIView):
    throttle_classes: ClassVar[list[type]] = [ScopedRateThrottle]
    throttle_scope = "staff_password"

    @extend_schema(
        operation_id="staff_password_change",
        tags=AUTH_TAGS,
        summary="Change the password",
        description=(
            "Replaces the password of the signed-in member and clears `must_change_password`. "
            "The token stays valid. The new password follows the same strength rules as the "
            "admin and must differ from the current one: a wrong current password is a `400` "
            "on `current_password` (`password_incorrect`), a weak or unchanged new one is a "
            "`400` on `new_password` (`password_too_short`, `password_too_common`, "
            "`password_entirely_numeric`, `password_too_similar`, `password_unchanged`). "
            "Ten tries an hour. Every other staff call keeps working while "
            "`must_change_password` is true."
        ),
        request=StaffPasswordSerializer,
        responses={204: None},
    )
    def post(self, request: Request) -> Response:
        serializer = StaffPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        staff_auth.change_password(
            user=request.user,
            current_password=serializer.validated_data["current_password"],
            new_password=serializer.validated_data["new_password"],
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class StaffMeView(StaffAPIView):
    @extend_schema(
        operation_id="staff_me",
        tags=STAFF_TAGS,
        summary="Read the signed-in member",
        description=(
            "The member, their role and permission codes, whether they must change the "
            "password, and the restaurant they work for (name, logo, position and the "
            "optional `service_radius_m`, absent when the restaurant sets none). "
            "`403 permission_denied` means the account is not an active member of a "
            "restaurant any more."
        ),
        responses={200: StaffMeSerializer},
    )
    def get(self, request: Request) -> Response:
        membership = get_membership(request)
        user = membership.user
        data: dict[str, Any] = {
            "id": user.pk,
            "username": user.username,
            "full_name": user.full_name,
            "role": membership.role,
            "permissions": sorted(
                permission.value for permission in permissions_for_role(membership.role)
            ),
            "must_change_password": user.must_change_password,
            "restaurant": membership.restaurant,
        }
        return Response(StaffMeSerializer(data, context={"request": request}).data)
