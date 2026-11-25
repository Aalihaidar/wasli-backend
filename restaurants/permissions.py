from typing import Any, ClassVar, cast

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from core.permissions import Permission, role_has_permission

from .models import StaffMembership
from .services import resolve_membership


class HasRestaurantPermission(BasePermission):  # type: ignore[misc]
    """Lets a request through only when the caller is an active member of a restaurant whose
    role grants ``required_permission``. The role name is never compared here.

    The restaurant comes from the ``restaurant_slug`` URL argument when the view has one,
    otherwise from the caller's only membership. The membership that was used is kept on the
    request: read it with ``get_membership(request)`` and scope every query with
    ``for_restaurant(membership.restaurant)``.
    """

    required_permission: ClassVar[Permission]

    def has_permission(self, request: Request, view: Any) -> bool:
        user = request.user
        if user is None or not user.is_authenticated:
            return False
        slug = getattr(view, "kwargs", {}).get("restaurant_slug")
        membership = resolve_membership(user, slug)
        if membership is None or not role_has_permission(
            membership.role, self.required_permission
        ):
            return False
        request.staff_membership = membership
        return True


class IsStaffMember(BasePermission):  # type: ignore[misc]
    """Lets a request through when the caller is an active member of a restaurant, whatever
    the role. For the calls every member needs (their own profile and their own password).

    A caller without a token is turned away by the authentication class (401); a signed-in
    account without an active membership (for example a member deactivated after signing in)
    is a 403 here. The membership is kept on the request: read it with ``get_membership``.
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        user = request.user
        if user is None or not user.is_authenticated:
            return False
        membership = resolve_membership(user)
        if membership is None:
            return False
        request.staff_membership = membership
        return True


def require_permission(permission: Permission) -> type[HasRestaurantPermission]:
    """A permission class for one code: ``permission_classes = [require_permission(...)]``."""
    return type(
        f"Requires_{permission.name}",
        (HasRestaurantPermission,),
        {"required_permission": permission},
    )


def get_membership(request: Request) -> StaffMembership:
    """The membership ``HasRestaurantPermission`` accepted for this request."""
    return cast("StaffMembership", request.staff_membership)
