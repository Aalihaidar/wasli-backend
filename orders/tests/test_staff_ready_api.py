"""``POST /staff/orders/{id}/ready``: an accepted order is ready and on its way to the car, and the
customer's chat says so in the same step."""

from typing import Any

import pytest
from rest_framework.test import APIClient

from chat.models import Message, MessageKind, Sender
from chat.tests.helpers import signed_in
from core.permissions import ROLE_PERMISSIONS, Permission, Role
from orders.models import Order, OrderEvent, OrderStatus
from orders.services import mark_order_ready
from orders.tests.factories import make_order
from orders.tests.test_staff_decision_api import (
    Shop,
    accept,
    first_error,
    headers_of,
    reject,
    results,
)
from restaurants.models import StaffMembership
from restaurants.tests.factories import make_member

pytestmark = pytest.mark.django_db


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def ready(api: APIClient, member: StaffMembership, order: Order) -> Any:
    return api.post(
        f"/api/v1/staff/orders/{order.pk}/ready",
        {},
        format="json",
        headers=headers_of(member),
    )


def accepted_shop(api: APIClient, **kwargs: str) -> Shop:
    shop = Shop(**kwargs)
    assert accept(api, shop.cashier, shop.order, {"eta_minutes": 10}).status_code == 200
    return shop


class TestReady:
    def test_an_accepted_order_becomes_ready_and_the_updated_order_comes_back(
        self, api: APIClient
    ) -> None:
        shop = accepted_shop(api)

        response = ready(api, shop.cashier, shop.order)

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(shop.order.pk)
        assert body["status"] == "ready"
        assert body["ready_at"] is not None
        assert body["eta_minutes"] == 10
        assert body["decided_at"] is not None
        stored = Order.objects.get(pk=shop.order.pk)
        assert stored.status == OrderStatus.READY and stored.ready_at is not None

    def test_the_change_moves_updated_at_so_the_screens_find_it(
        self, api: APIClient
    ) -> None:
        shop = accepted_shop(api)
        before = Order.objects.get(pk=shop.order.pk).updated_at

        ready(api, shop.cashier, shop.order)

        assert Order.objects.get(pk=shop.order.pk).updated_at > before

    def test_one_event_names_the_member_and_the_two_states(
        self, api: APIClient
    ) -> None:
        shop = accepted_shop(api)

        ready(api, shop.cashier, shop.order)

        event = OrderEvent.objects.get(order=shop.order, to_status="ready")
        assert event.from_status == "accepted"
        assert event.actor_id == shop.cashier.user.pk

    def test_an_unanswered_order_has_no_ready_time_in_the_list(
        self, api: APIClient
    ) -> None:
        shop = Shop()

        listing = api.get(
            "/api/v1/staff/orders", headers=headers_of(shop.cashier)
        ).json()

        assert listing["orders"][0]["ready_at"] is None


class TestTheCustomerIsTold:
    def test_the_message_carries_only_the_order_and_its_status(
        self, api: APIClient
    ) -> None:
        shop = accepted_shop(api)

        ready(api, shop.cashier, shop.order)

        accepted, done = results(shop.order)
        assert accepted.payload["status"] == "accepted"
        assert done.sender == Sender.BOT
        assert done.payload == {
            "order_id": str(shop.order.pk),
            "number": shop.order.number,
            "status": "ready",
        }
        assert "ready" in done.text and "#1" in done.text
        assert done.seq == accepted.seq + 1

    def test_the_text_follows_the_conversations_language(self, api: APIClient) -> None:
        shop = accepted_shop(api, locale="ar")

        ready(api, shop.cashier, shop.order)

        _, done = results(shop.order)
        assert "جاهز" in done.text  # "ready"

    def test_the_customer_reads_the_message_and_the_status(
        self, api: APIClient
    ) -> None:
        shop = Shop()
        customer, customer_api = signed_in("sara-ready@example.com")
        from chat.tests.factories import make_conversation

        conversation = make_conversation(shop.restaurant, customer)
        order = make_order(conversation=conversation)
        accept(api, shop.cashier, order, {"eta_minutes": 5})

        ready(api, shop.cashier, order)

        body = customer_api.get(
            f"/api/v1/conversations/{conversation.pk}/messages"
        ).json()
        last = body["messages"][-1]
        assert (last["sender"], last["kind"]) == ("bot", "result")
        assert last["payload"]["status"] == "ready"
        assert body["conversation"]["order"]["status"] == "ready"
        assert (
            customer_api.get(f"/api/v1/orders/{order.pk}").json()["status"] == "ready"
        )


class TestOnlyAnAcceptedOrderCanBeReady:
    def test_a_placed_order_is_a_409_and_nothing_is_posted(
        self, api: APIClient
    ) -> None:
        shop = Shop()

        response = ready(api, shop.cashier, shop.order)

        assert response.status_code == 409
        assert first_error(response)["code"] == "order_invalid_transition"
        assert Order.objects.get(pk=shop.order.pk).status == OrderStatus.PLACED
        assert results(shop.order) == []

    def test_a_rejected_order_is_a_409(self, api: APIClient) -> None:
        shop = Shop()
        reject(api, shop.cashier, shop.order, {"reason_code": "too_busy"})

        response = ready(api, shop.cashier, shop.order)

        assert response.status_code == 409
        assert len(results(shop.order)) == 1

    def test_an_order_is_made_ready_once(self, api: APIClient) -> None:
        shop = accepted_shop(api)
        ready(api, shop.cashier, shop.order)

        again = ready(api, shop.cashier, shop.order)

        assert again.status_code == 409
        assert len(results(shop.order)) == 2  # accepted, then ready: no third message

    def test_a_ready_order_cannot_be_answered_again(self, api: APIClient) -> None:
        shop = accepted_shop(api)
        ready(api, shop.cashier, shop.order)

        accepted = accept(api, shop.cashier, shop.order, {"eta_minutes": 5})
        rejected = reject(api, shop.cashier, shop.order, {"reason_code": "too_busy"})

        assert accepted.status_code == 409 and rejected.status_code == 409
        assert Order.objects.get(pk=shop.order.pk).status == OrderStatus.READY

    def test_when_the_message_cannot_be_posted_the_order_stays_accepted(
        self, api: APIClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        shop = accepted_shop(api)

        def broken(order: Order) -> Message:
            raise RuntimeError("the chat is down")

        monkeypatch.setattr("orders.services.post_order_result", broken)

        with pytest.raises(RuntimeError):
            mark_order_ready(
                order_id=shop.order.pk,
                restaurant=shop.restaurant,
                actor=shop.cashier.user,
            )

        stored = Order.objects.get(pk=shop.order.pk)
        assert stored.status == OrderStatus.ACCEPTED and stored.ready_at is None
        assert not OrderEvent.objects.filter(
            order=shop.order, to_status="ready"
        ).exists()
        assert (
            Message.objects.filter(
                conversation=shop.order.conversation, kind=MessageKind.RESULT
            ).count()
            == 1
        )


class TestWhoMayDoIt:
    def test_no_token_is_a_401(self, api: APIClient) -> None:
        shop = accepted_shop(api)

        response = api.post(
            f"/api/v1/staff/orders/{shop.order.pk}/ready", {}, format="json"
        )

        assert response.status_code == 401

    def test_a_member_without_orders_decide_is_a_403_and_nothing_changes(
        self, api: APIClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        shop = accepted_shop(api)
        monkeypatch.setitem(
            ROLE_PERMISSIONS, Role.CASHIER, frozenset({Permission.ORDERS_VIEW})
        )

        response = ready(api, shop.cashier, shop.order)

        assert response.status_code == 403
        assert Order.objects.get(pk=shop.order.pk).status == OrderStatus.ACCEPTED

    def test_an_admin_may_do_it_too(self, api: APIClient) -> None:
        shop = accepted_shop(api)
        admin = make_member(shop.restaurant, "cafe-one-admin", Role.ADMIN)

        assert ready(api, admin, shop.order).status_code == 200

    def test_another_restaurants_order_is_a_404_and_stays_untouched(
        self, api: APIClient
    ) -> None:
        mine = Shop("cafe-one")
        theirs = accepted_shop(api, slug="cafe-two")

        response = ready(api, mine.cashier, theirs.order)

        assert response.status_code == 404
        assert Order.objects.get(pk=theirs.order.pk).status == OrderStatus.ACCEPTED
        assert len(results(theirs.order)) == 1
