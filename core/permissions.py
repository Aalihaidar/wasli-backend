"""Permission codes and the role map.

Access is decided by a permission code, never by a role name: a view asks "may this member
do ``orders.decide``?", and the role map below says which roles have which codes. Adding a
role later means adding a row here, not editing every view.
"""

from enum import StrEnum


class Permission(StrEnum):
    ORDERS_VIEW = "orders.view"
    ORDERS_DECIDE = "orders.decide"
    MENU_EDIT = "menu.edit"  # items, prices, photos, availability
    MEMBERS_MANAGE = "members.manage"
    RESTAURANT_SETTINGS = "restaurant.settings"
    REPORTS_VIEW = "reports.view"


class Role(StrEnum):
    """A member's role inside one restaurant (``StaffMembership.role``)."""

    ADMIN = "admin"
    CASHIER = "cashier"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.CASHIER: frozenset({Permission.ORDERS_VIEW, Permission.ORDERS_DECIDE}),
}


def permissions_for_role(role: str) -> frozenset[Permission]:
    """Permission codes of a role; an unknown role has none."""
    try:
        return ROLE_PERMISSIONS[Role(role)]
    except ValueError, KeyError:
        return frozenset()


def role_has_permission(role: str, permission: Permission) -> bool:
    return permission in permissions_for_role(role)
