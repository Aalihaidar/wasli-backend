import pytest

from core.permissions import (
    ROLE_PERMISSIONS,
    Permission,
    Role,
    permissions_for_role,
    role_has_permission,
)


def test_the_six_permission_codes() -> None:
    assert {p.value for p in Permission} == {
        "orders.view",
        "orders.decide",
        "menu.edit",
        "members.manage",
        "restaurant.settings",
        "reports.view",
    }


def test_the_roles() -> None:
    assert {r.value for r in Role} == {"admin", "cashier"}


def test_an_admin_has_every_permission() -> None:
    assert permissions_for_role("admin") == frozenset(Permission)


def test_a_cashier_only_sees_and_decides_orders() -> None:
    assert permissions_for_role("cashier") == {
        Permission.ORDERS_VIEW,
        Permission.ORDERS_DECIDE,
    }


@pytest.mark.parametrize(
    "permission",
    [
        Permission.MENU_EDIT,
        Permission.MEMBERS_MANAGE,
        Permission.RESTAURANT_SETTINGS,
        Permission.REPORTS_VIEW,
    ],
)
def test_a_cashier_cannot_do_what_only_an_admin_can(permission: Permission) -> None:
    assert role_has_permission("admin", permission) is True
    assert role_has_permission("cashier", permission) is False


@pytest.mark.parametrize("role", ["", "owner", "ADMIN", "waiter"])
def test_an_unknown_role_has_no_permission(role: str) -> None:
    assert permissions_for_role(role) == frozenset()


def test_every_role_is_in_the_map() -> None:
    assert set(ROLE_PERMISSIONS) == set(Role)
