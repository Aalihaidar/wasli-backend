"""``GET /staff/orders``: the restaurant screen's polling list, scoped to the member's own
restaurant."""

from datetime import timedelta
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.permissions import ROLE_PERMISSIONS, Role
from customers.tests.factories import make_customer
from orders.models import Order
from orders.services import accept_order, reject_order
from orders.tests.factories import make_order, make_order_item
from restaurants.models import Restaurant, StaffMembership
from restaurants.services import screen_is_online
from restaurants.tests.factories import make_member, make_restaurant

pytestmark = pytest.mark.django_db

URL = "/api/v1/staff/orders"


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def headers_of(member: StaffMembership) -> dict[str, str]:
    token, _ = Token.objects.get_or_create(user=member.user)
    return {"Authorization": f"Token {token.key}"}


def a_restaurant(slug: str = "cafe-one") -> tuple[Restaurant, StaffMembership]:
    restaurant = make_restaurant(slug)
    return restaurant, make_member(restaurant, f"{slug}-cashier")


def listing(api: APIClient, member: StaffMembership, query: str = "") -> Any:
    return api.get(f"{URL}{query}", headers=headers_of(member))


def ids(response: Any) -> list[str]:
    return [order["id"] for order in response.json()["orders"]]


def first_error(response: Any) -> dict[str, Any]:
    return dict(response.json()["errors"][0])


def iso(moment: Any) -> str:
    """A time the way the API writes it (``Z``): a ``+00:00`` would turn into a space in a URL."""
    return str(moment.isoformat().replace("+00:00", "Z"))


def changed_at(order: Order, when: Any) -> None:
    """Move ``updated_at`` (the model only sets it on ``save``)."""
    Order.objects.filter(pk=order.pk).update(updated_at=when)


class TestAccess:
    def test_it_needs_a_token(self, api: APIClient) -> None:
        response = api.get(URL)

        assert response.status_code == 401
        assert first_error(response)["code"] == "not_authenticated"

    def test_a_customer_token_does_not_open_it(self, api: APIClient) -> None:
        response = api.get(URL, headers={"Authorization": "Customer abc"})

        assert response.status_code == 401

    def test_an_account_that_is_no_longer_a_member_is_forbidden(
        self, api: APIClient
    ) -> None:
        _, member = a_restaurant()
        headers = headers_of(member)
        StaffMembership.objects.update(is_active=False)

        response = api.get(URL, headers=headers)

        assert response.status_code == 403
        assert first_error(response)["code"] == "permission_denied"

    def test_the_permission_is_checked_by_code_not_by_role_name(
        self, api: APIClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        restaurant, member = a_restaurant()
        monkeypatch.setitem(ROLE_PERMISSIONS, Role.CASHIER, frozenset())

        response = listing(api, member)

        assert response.status_code == 403
        restaurant.refresh_from_db()
        assert restaurant.screen_last_seen_at is None

    def test_an_admin_and_a_cashier_both_read_the_list(self, api: APIClient) -> None:
        restaurant, cashier = a_restaurant()
        admin = make_member(restaurant, "cafe-one-admin", Role.ADMIN)
        order = make_order(restaurant)

        assert ids(listing(api, cashier)) == [str(order.pk)]
        assert ids(listing(api, admin)) == [str(order.pk)]

    def test_the_answer_is_never_cached(self, api: APIClient) -> None:
        _, member = a_restaurant()

        assert listing(api, member)["Cache-Control"] == "no-store"


class TestTenancy:
    def test_each_restaurant_sees_only_its_own_orders(self, api: APIClient) -> None:
        restaurant_a, member_a = a_restaurant("cafe-a")
        restaurant_b, member_b = a_restaurant("cafe-b")
        order_a = make_order(restaurant_a)
        order_b = make_order(restaurant_b)

        assert ids(listing(api, member_a)) == [str(order_a.pk)]
        assert ids(listing(api, member_b)) == [str(order_b.pk)]

    def test_a_restaurant_with_orders_of_others_only_gets_an_empty_list(
        self, api: APIClient
    ) -> None:
        _, member = a_restaurant("cafe-a")
        make_order(a_restaurant("cafe-b")[0])

        assert listing(api, member).json()["orders"] == []

    def test_only_the_calling_restaurant_is_marked_online(self, api: APIClient) -> None:
        restaurant_a, member_a = a_restaurant("cafe-a")
        restaurant_b, _ = a_restaurant("cafe-b")

        listing(api, member_a)

        restaurant_a.refresh_from_db()
        restaurant_b.refresh_from_db()
        assert screen_is_online(restaurant_a)
        assert restaurant_b.screen_last_seen_at is None


class TestShape:
    def an_order(self, restaurant: Restaurant, **extra: Any) -> Order:
        order = make_order(restaurant, **extra)
        make_order_item(
            order,
            1,
            options=[
                {"name_en": "Less sugar", "name_ar": "سكر أقل", "price_delta_minor": 0}
            ],
        )
        make_order_item(
            order,
            2,
            name_en="Cheese sandwich",
            name_ar="ساندويتش جبن",
            unit_price_minor=1200,
            quantity=1,
            line_total_minor=1200,
            note="No tomato",
        )
        return order

    def test_a_placed_order_with_a_position(self, api: APIClient) -> None:
        restaurant, member = a_restaurant()
        restaurant.service_radius_m = 300
        restaurant.save()
        captured = timezone.now() - timedelta(seconds=5)
        order = self.an_order(
            restaurant,
            customer_note="Please bring napkins.",
            customer_lat=25.2002,
            customer_lng=55.2702,
            location_accuracy_m=15.0,
            location_source="gps",
            location_captured_at=captured,
            distance_m=21,
        )

        response = listing(api, member)

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"server_time", "orders"}
        assert body["orders"] == [
            {
                "id": str(order.pk),
                "number": 1,
                "status": "placed",
                "order_type": "car",
                "placed_at": body["orders"][0]["placed_at"],
                "updated_at": body["orders"][0]["updated_at"],
                "decided_at": None,
                "ready_at": None,
                "eta_minutes": None,
                "rejection_reason_code": None,
                "rejection_note": None,
                "items": [
                    {
                        "line": 1,
                        "name_en": "Karak tea",
                        "name_ar": "شاي كرك",
                        "quantity": 2,
                        "unit_price_minor": 300,
                        "options": [
                            {
                                "name_en": "Less sugar",
                                "name_ar": "سكر أقل",
                                "price_delta_minor": 0,
                            }
                        ],
                        "note": "",
                        "line_total_minor": 600,
                    },
                    {
                        "line": 2,
                        "name_en": "Cheese sandwich",
                        "name_ar": "ساندويتش جبن",
                        "quantity": 1,
                        "unit_price_minor": 1200,
                        "options": [],
                        "note": "No tomato",
                        "line_total_minor": 1200,
                    },
                ],
                "customer_note": "Please bring napkins.",
                "subtotal_minor": 600,
                "total_minor": 600,
                "currency": "AED",
                "vehicle": {
                    "plate": "A 12345",
                    "model": "Toyota Camry",
                    "colour": "White",
                },
                "parking_note": "Parking B2 near the lift",
                "customer_location": {
                    "lat": 25.2002,
                    "lng": 55.2702,
                    "accuracy_m": 15.0,
                    "source": "gps",
                    "captured_at": body["orders"][0]["customer_location"][
                        "captured_at"
                    ],
                },
                "distance_m": 21,
                "distance_band": "in_lot",
            }
        ]

    def test_without_a_position_the_location_is_absent_and_the_band_unknown(
        self, api: APIClient
    ) -> None:
        restaurant, member = a_restaurant()
        self.an_order(restaurant)

        order = listing(api, member).json()["orders"][0]

        assert "customer_location" not in order
        assert order["distance_m"] is None
        assert order["distance_band"] == "unknown"
        assert order["vehicle"]["plate"] == "A 12345"
        assert order["parking_note"] == "Parking B2 near the lift"

    @pytest.mark.parametrize(
        ("distance", "band"), [(100, "in_lot"), (600, "near"), (5000, "far")]
    )
    def test_the_band_follows_the_service_distance(
        self, api: APIClient, distance: int, band: str
    ) -> None:
        restaurant, member = a_restaurant()
        restaurant.service_radius_m = 300
        restaurant.save()
        make_order(restaurant, distance_m=distance)

        order = listing(api, member).json()["orders"][0]

        assert (order["distance_m"], order["distance_band"]) == (distance, band)

    def test_the_order_note_and_the_text_fields_are_never_null(
        self, api: APIClient
    ) -> None:
        restaurant, member = a_restaurant()
        self.an_order(restaurant)

        order = listing(api, member).json()["orders"][0]

        assert order["customer_note"] == ""
        assert order["items"][0]["note"] == ""

    def test_no_personal_detail_of_the_customer_is_sent(self, api: APIClient) -> None:
        restaurant, member = a_restaurant()
        customer = make_customer("sara.private@example.com", "Sara Private")
        order = self.an_order(restaurant)
        Order.objects.filter(pk=order.pk).update(customer=customer)
        customer.user.phone = "+971500000777"
        customer.user.save()

        text = listing(api, member).content.decode()

        assert "Sara Private" not in text
        assert "sara.private@example.com" not in text
        assert "971500000777" not in text
        assert '"customer"' not in text

    def test_an_accepted_order_shows_the_answer(self, api: APIClient) -> None:
        restaurant, member = a_restaurant()
        order = make_order(restaurant)
        accept_order(
            order_id=order.pk,
            restaurant=restaurant,
            actor=member.user,
            eta_minutes=15,
        )

        body = listing(api, member).json()["orders"][0]

        assert body["status"] == "accepted"
        assert body["eta_minutes"] == 15
        assert body["decided_at"] is not None
        assert body["rejection_reason_code"] is None

    def test_a_rejected_order_shows_the_reason_and_the_note(
        self, api: APIClient
    ) -> None:
        restaurant, member = a_restaurant()
        order = make_order(restaurant)
        reject_order(
            order_id=order.pk,
            restaurant=restaurant,
            actor=member.user,
            reason_code="other",
            note="The grill is closed.",
        )

        body = listing(api, member).json()["orders"][0]

        assert body["status"] == "rejected"
        assert body["rejection_reason_code"] == "other"
        assert body["rejection_note"] == "The grill is closed."
        assert body["eta_minutes"] is None
        assert body["decided_at"] is not None

    def test_the_newest_order_comes_first(self, api: APIClient) -> None:
        restaurant, member = a_restaurant()
        now = timezone.now()
        old = make_order(restaurant, placed_at=now - timedelta(minutes=30))
        new = make_order(restaurant, placed_at=now - timedelta(minutes=1))
        middle = make_order(restaurant, placed_at=now - timedelta(minutes=10))

        assert ids(listing(api, member)) == [str(new.pk), str(middle.pk), str(old.pk)]

    def test_the_list_does_not_ask_the_database_per_order(self, api: APIClient) -> None:
        restaurant, member = a_restaurant()
        for _ in range(5):
            self.an_order(restaurant)
        headers = headers_of(member)

        with CaptureQueriesContext(connection) as queries:
            response = api.get(URL, headers=headers)

        assert len(response.json()["orders"]) == 5
        assert len(queries) <= 8


class TestSinceAndTheServerTime:
    def test_the_server_time_is_now(self, api: APIClient) -> None:
        _, member = a_restaurant()
        before = timezone.now()

        server_time = parse_datetime(listing(api, member).json()["server_time"])

        assert server_time is not None
        assert before - timedelta(seconds=1) <= server_time <= timezone.now()

    def test_nothing_new_is_an_empty_list_with_a_server_time(
        self, api: APIClient
    ) -> None:
        restaurant, member = a_restaurant()
        make_order(restaurant)
        since = iso(timezone.now())
        order = Order.objects.get()
        changed_at(order, timezone.now() - timedelta(hours=1))

        body = listing(api, member, f"?since={since}").json()

        assert body["orders"] == []
        assert body["server_time"]

    def test_without_since_the_last_24_hours(self, api: APIClient) -> None:
        restaurant, member = a_restaurant()
        recent = make_order(restaurant)
        old = make_order(restaurant)
        changed_at(old, timezone.now() - timedelta(hours=25))

        assert ids(listing(api, member)) == [str(recent.pk)]

    def test_only_orders_changed_after_since(self, api: APIClient) -> None:
        restaurant, member = a_restaurant()
        before = make_order(restaurant)
        after = make_order(restaurant)
        since = timezone.now() - timedelta(minutes=5)
        changed_at(before, since - timedelta(minutes=1))
        changed_at(after, since + timedelta(minutes=1))

        assert ids(listing(api, member, f"?since={iso(since)}")) == [str(after.pk)]

    def test_a_change_just_before_since_is_read_again_and_an_old_one_is_not(
        self, api: APIClient
    ) -> None:
        """A change commits a moment after it is saved, so one saved a few seconds before the
        last ``server_time`` may not have been in the last answer: it is sent once more."""
        restaurant, member = a_restaurant()
        late = make_order(restaurant)
        settled = make_order(restaurant)
        since = timezone.now() - timedelta(minutes=5)
        changed_at(late, since - timedelta(seconds=5))
        changed_at(settled, since - timedelta(seconds=30))

        assert ids(listing(api, member, f"?since={iso(since)}")) == [str(late.pk)]

    def test_an_order_answered_after_the_last_poll_comes_back_changed(
        self, api: APIClient
    ) -> None:
        restaurant, member = a_restaurant()
        order = make_order(restaurant)
        first = listing(api, member).json()
        accept_order(
            order_id=order.pk,
            restaurant=restaurant,
            actor=member.user,
            eta_minutes=5,
        )

        second = listing(api, member, f"?since={first['server_time']}").json()

        assert [o["id"] for o in second["orders"]] == [str(order.pk)]
        assert second["orders"][0]["status"] == "accepted"
        assert second["orders"][0]["updated_at"] > first["orders"][0]["updated_at"]

    def test_the_same_unchanged_order_comes_again_with_the_same_updated_at(
        self, api: APIClient
    ) -> None:
        restaurant, member = a_restaurant()
        make_order(restaurant)
        first = listing(api, member).json()

        second = listing(api, member, f"?since={first['server_time']}").json()

        assert second["orders"] == first["orders"]

    def test_the_times_keep_their_microseconds(self, api: APIClient) -> None:
        restaurant, member = a_restaurant()
        make_order(restaurant)

        body = listing(api, member).json()

        for value in (body["server_time"], body["orders"][0]["updated_at"]):
            assert "." in value and value.endswith("Z")

    @pytest.mark.parametrize("since", ["yesterday", "12", "2026-13-45T00:00:00Z"])
    def test_a_since_that_is_not_a_timestamp_is_refused(
        self, api: APIClient, since: str
    ) -> None:
        restaurant, member = a_restaurant()

        response = listing(api, member, f"?since={since}")

        assert response.status_code == 400
        error = first_error(response)
        assert (error["code"], error["attr"]) == ("invalid_since", "since")
        restaurant.refresh_from_db()
        assert restaurant.screen_last_seen_at is None

    def test_a_since_in_the_future_is_refused(self, api: APIClient) -> None:
        _, member = a_restaurant()
        future = (
            (timezone.now() + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        )

        response = listing(api, member, f"?since={future}")

        assert response.status_code == 400
        assert first_error(response)["code"] == "invalid_since"


class TestTheScreenIsMarkedOnline:
    def test_a_successful_call_marks_the_screen_online(self, api: APIClient) -> None:
        restaurant, member = a_restaurant()
        assert not screen_is_online(restaurant)

        listing(api, member)

        restaurant.refresh_from_db()
        assert screen_is_online(restaurant)

    def test_the_mark_is_the_time_of_the_call(self, api: APIClient) -> None:
        restaurant, member = a_restaurant()
        body = listing(api, member).json()

        restaurant.refresh_from_db()
        assert restaurant.screen_last_seen_at == parse_datetime(body["server_time"])

    def test_an_empty_answer_marks_it_too(self, api: APIClient) -> None:
        restaurant, member = a_restaurant()
        assert listing(api, member).json()["orders"] == []

        restaurant.refresh_from_db()
        assert screen_is_online(restaurant)

    def test_a_refused_call_does_not_mark_it(self, api: APIClient) -> None:
        restaurant, member = a_restaurant()

        api.get(URL)  # no token
        listing(api, member, "?since=nonsense")  # bad query

        restaurant.refresh_from_db()
        assert restaurant.screen_last_seen_at is None

    def test_nothing_else_of_the_restaurant_changes(self, api: APIClient) -> None:
        restaurant, member = a_restaurant()
        before = Restaurant.objects.get(pk=restaurant.pk)

        listing(api, member)

        after = Restaurant.objects.get(pk=restaurant.pk)
        assert after.updated_at == before.updated_at
        assert after.next_order_number == before.next_order_number

    def test_customers_see_the_restaurant_as_open_after_a_poll(
        self, api: APIClient, settings: Any
    ) -> None:
        settings.REQUIRE_SCREEN_ONLINE = True
        restaurant, member = a_restaurant()
        nearby = f"/api/v1/restaurants/nearby?lat={restaurant.latitude}&lng={restaurant.longitude}"
        assert api.get(nearby).json()["restaurants"] == []

        listing(api, member)

        slugs = [r["slug"] for r in api.get(nearby).json()["restaurants"]]
        assert slugs == [restaurant.slug]
