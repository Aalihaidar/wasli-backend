"""A sweep over every route of the API, so a new endpoint cannot slip past the rules.

- Every route is throttled (the defaults of ``REST_FRAMEWORK`` unless a view sets its own).
- Every staff route refuses a call with no token (``401``) and a customer's token.
- Every staff route that names an order answers ``404`` to a member of another restaurant and
  changes nothing. A new such route fails the sweep until its valid body is added below, so it
  cannot be forgotten.
"""

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from django.urls import URLPattern, URLResolver
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from chat.tests.helpers import signed_in
from config import api_urls
from orders.models import Order, OrderStatus
from orders.tests.factories import make_order
from restaurants.tests.factories import make_member, make_restaurant

API = "/api/v1/"

# Open to everyone on purpose (checked by the tests of their own apps): the staff sign-in.
STAFF_PUBLIC_ROUTES = {"auth/login"}

# A valid body for each staff route that acts on one order, by the end of its route.
ORDER_ROUTE_BODIES: dict[str, dict[str, Any]] = {
    "accept": {"eta_minutes": 10},
    "reject": {"reason_code": "too_busy"},
}


def walk(patterns: Any, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Every route as ``(route, view class)``."""
    for pattern in patterns:
        route = prefix + str(pattern.pattern)
        if isinstance(pattern, URLResolver):
            yield from walk(pattern.url_patterns, route)
        elif isinstance(pattern, URLPattern):
            view = getattr(pattern.callback, "cls", None)
            if view is not None:
                yield route, view


ROUTES = list(walk(api_urls.urlpatterns))


def methods_of(view: Any) -> list[str]:
    return [
        method
        for method in view.http_method_names
        if method not in {"options", "head"} and hasattr(view, method)
    ]


def staff_routes() -> list[tuple[str, Any]]:
    return [
        (route, view)
        for route, view in ROUTES
        if (route.startswith("staff/") or route.startswith("auth/"))
        and route not in STAFF_PUBLIC_ROUTES
    ]


def url_of(route: str, order_id: object | None = None) -> str:
    return API + route.replace("<uuid:id>", str(order_id or uuid4()))


def test_the_sweep_finds_the_routes() -> None:
    routes = {route for route, _ in ROUTES}

    assert {"staff/orders", "auth/logout", "customers/login"} <= routes
    assert len(routes) > 20


@pytest.mark.parametrize(("route", "view"), ROUTES, ids=[r for r, _ in ROUTES])
def test_every_route_is_throttled(route: str, view: Any) -> None:
    assert view.throttle_classes, f"{route} has no throttle"


@pytest.mark.django_db
class TestTheStaffRoutes:
    @pytest.fixture
    def api(self) -> APIClient:
        return APIClient()

    @pytest.mark.parametrize(
        ("route", "view"), staff_routes(), ids=[r for r, _ in staff_routes()]
    )
    def test_no_token_is_a_401(self, api: APIClient, route: str, view: Any) -> None:
        for method in methods_of(view):
            response = getattr(api, method)(url_of(route), {}, format="json")

            assert response.status_code == 401, f"{method.upper()} {route}"

    @pytest.mark.parametrize(
        ("route", "view"), staff_routes(), ids=[r for r, _ in staff_routes()]
    )
    def test_a_customers_token_is_refused(self, route: str, view: Any) -> None:
        _, customer_api = signed_in("sara-sweep@example.com")

        for method in methods_of(view):
            response = getattr(customer_api, method)(url_of(route), {}, format="json")

            assert response.status_code in {401, 403}, f"{method.upper()} {route}"

    def test_a_member_of_another_restaurant_gets_a_404_and_changes_nothing(
        self, api: APIClient
    ) -> None:
        mine = make_restaurant("cafe-one")
        theirs = make_restaurant("cafe-two")
        outsider = make_member(mine, "cafe-one-cashier")
        order = make_order(theirs)
        token, _ = Token.objects.get_or_create(user=outsider.user)
        headers = {"Authorization": f"Token {token.key}"}
        by_id = [(r, v) for r, v in staff_routes() if "<uuid:id>" in r]
        assert by_id, "the sweep found no staff route that names an order"

        for route, view in by_id:
            body = ORDER_ROUTE_BODIES.get(route.rsplit("/", 1)[-1])
            assert body is not None, (
                f"add a valid body for {route} to ORDER_ROUTE_BODIES"
            )
            for method in methods_of(view):
                response = getattr(api, method)(
                    url_of(route, order.pk), body, format="json", headers=headers
                )

                assert response.status_code == 404, f"{method.upper()} {route}"
        stored = Order.objects.get(pk=order.pk)
        assert stored.status == OrderStatus.PLACED
        assert stored.updated_at == order.updated_at
