"""``POST /staff/orders/{id}/accept`` and ``/reject``: the restaurant's answer, the ``result``
message the customer receives in the same step, and the isolation between restaurants."""

from typing import Any

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from chat.models import Message, MessageKind, Sender
from chat.tests.factories import make_conversation
from chat.tests.helpers import signed_in
from core.permissions import ROLE_PERMISSIONS, Permission, Role
from orders.models import Order, OrderEvent, OrderStatus
from orders.services import accept_order
from orders.tests.factories import make_order
from restaurants.models import StaffMembership
from restaurants.tests.factories import make_member, make_restaurant

pytestmark = pytest.mark.django_db


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def headers_of(member: StaffMembership) -> dict[str, str]:
    token, _ = Token.objects.get_or_create(user=member.user)
    return {"Authorization": f"Token {token.key}"}


def accept(
    api: APIClient, member: StaffMembership, order: Order, body: dict[str, Any]
) -> Any:
    return api.post(
        f"/api/v1/staff/orders/{order.pk}/accept",
        body,
        format="json",
        headers=headers_of(member),
    )


def reject(
    api: APIClient, member: StaffMembership, order: Order, body: dict[str, Any]
) -> Any:
    return api.post(
        f"/api/v1/staff/orders/{order.pk}/reject",
        body,
        format="json",
        headers=headers_of(member),
    )


def first_error(response: Any) -> dict[str, Any]:
    return dict(response.json()["errors"][0])


def results(order: Order) -> list[Message]:
    return list(
        Message.objects.filter(conversation=order.conversation, kind=MessageKind.RESULT)
    )


class Shop:
    """A restaurant, its cashier and one placed order in an English conversation."""

    def __init__(self, slug: str = "cafe-one", locale: str = "en") -> None:
        self.restaurant = make_restaurant(slug)
        self.cashier = make_member(self.restaurant, f"{slug}-cashier")
        self.order = make_order(
            conversation=make_conversation(self.restaurant, locale=locale)
        )


class TestAccept:
    def test_the_order_is_accepted_and_the_updated_order_comes_back(
        self, api: APIClient
    ) -> None:
        shop = Shop()

        response = accept(api, shop.cashier, shop.order, {"eta_minutes": 10})

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(shop.order.pk)
        assert body["status"] == "accepted"
        assert body["eta_minutes"] == 10
        assert body["decided_at"] is not None
        assert Order.objects.get(pk=shop.order.pk).status == OrderStatus.ACCEPTED

    def test_the_customer_gets_a_result_message_with_only_the_accepted_fields(
        self, api: APIClient
    ) -> None:
        shop = Shop()

        accept(api, shop.cashier, shop.order, {"eta_minutes": 15})

        (message,) = results(shop.order)
        assert message.sender == Sender.BOT
        assert message.payload == {
            "order_id": str(shop.order.pk),
            "number": shop.order.number,
            "status": "accepted",
            "eta_minutes": 15,
        }
        assert "#1" in message.text and "15" in message.text

    def test_the_text_follows_the_conversations_language(self, api: APIClient) -> None:
        shop = Shop(locale="ar")

        accept(api, shop.cashier, shop.order, {"eta_minutes": 5})

        (message,) = results(shop.order)
        assert "قبول" in message.text  # "accepted"
        assert message.payload["eta_minutes"] == 5

    def test_the_message_takes_the_next_seq_of_the_conversation(
        self, api: APIClient
    ) -> None:
        shop = Shop()
        before = shop.order.conversation.last_seq

        accept(api, shop.cashier, shop.order, {"eta_minutes": 10})

        (message,) = results(shop.order)
        assert message.seq == before + 1
        shop.order.conversation.refresh_from_db()
        assert shop.order.conversation.last_seq == message.seq

    @pytest.mark.parametrize("body", [{"eta_minutes": 7}, {"eta_minutes": 0}, {}])
    def test_a_wrong_wait_is_a_400_and_nothing_is_posted(
        self, api: APIClient, body: dict[str, Any]
    ) -> None:
        shop = Shop()

        response = accept(api, shop.cashier, shop.order, body)

        assert response.status_code == 400
        assert first_error(response)["attr"] == "eta_minutes"
        assert Order.objects.get(pk=shop.order.pk).status == OrderStatus.PLACED
        assert results(shop.order) == []

    def test_an_order_is_answered_once_and_the_second_answer_posts_nothing(
        self, api: APIClient
    ) -> None:
        shop = Shop()
        accept(api, shop.cashier, shop.order, {"eta_minutes": 10})

        again = accept(api, shop.cashier, shop.order, {"eta_minutes": 5})
        rejected = reject(api, shop.cashier, shop.order, {"reason_code": "too_busy"})

        assert again.status_code == 409
        assert first_error(again)["code"] == "order_invalid_transition"
        assert rejected.status_code == 409
        assert len(results(shop.order)) == 1
        assert Order.objects.get(pk=shop.order.pk).eta_minutes == 10

    def test_one_event_names_the_member(self, api: APIClient) -> None:
        shop = Shop()

        accept(api, shop.cashier, shop.order, {"eta_minutes": 10})

        event = OrderEvent.objects.get(order=shop.order, to_status="accepted")
        assert event.actor_id == shop.cashier.user.pk


class TestReject:
    def test_a_reason_without_a_note(self, api: APIClient) -> None:
        shop = Shop()

        response = reject(api, shop.cashier, shop.order, {"reason_code": "too_busy"})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "rejected"
        assert body["rejection_reason_code"] == "too_busy"
        assert body["rejection_note"] is None
        (message,) = results(shop.order)
        assert message.payload == {
            "order_id": str(shop.order.pk),
            "number": shop.order.number,
            "status": "rejected",
            "rejection_reason_code": "too_busy",
        }
        assert "busy" in message.text

    def test_a_note_is_in_the_payload_and_the_text(self, api: APIClient) -> None:
        shop = Shop()

        reject(
            api,
            shop.cashier,
            shop.order,
            {"reason_code": "item_unavailable", "note": "  No more karak  "},
        )

        (message,) = results(shop.order)
        assert message.payload["rejection_note"] == "No more karak"
        assert "No more karak" in message.text
        assert "eta_minutes" not in message.payload

    def test_other_is_written_with_its_note_alone(self, api: APIClient) -> None:
        shop = Shop()

        reject(
            api,
            shop.cashier,
            shop.order,
            {"reason_code": "other", "note": "The oven is broken"},
        )

        (message,) = results(shop.order)
        assert message.payload["rejection_reason_code"] == "other"
        assert "The oven is broken" in message.text

    @pytest.mark.parametrize("reason", ["too_far", "location_unclear", "closing_soon"])
    def test_every_reason_has_a_text_in_both_languages(
        self, api: APIClient, reason: str
    ) -> None:
        english = Shop("cafe-en", "en")
        arabic = Shop("cafe-ar", "ar")

        reject(api, english.cashier, english.order, {"reason_code": reason})
        reject(api, arabic.cashier, arabic.order, {"reason_code": reason})

        (en,) = results(english.order)
        (ar,) = results(arabic.order)
        assert en.text and ar.text and en.text != ar.text

    @pytest.mark.parametrize(
        ("body", "attr", "code"),
        [
            ({"reason_code": "other"}, "note", "required"),
            ({"reason_code": "other", "note": "   "}, "note", "required"),
            ({"reason_code": "mood"}, "reason_code", "invalid_choice"),
            ({}, "reason_code", "required"),
            ({"reason_code": "too_busy", "note": "x" * 201}, "note", "max_length"),
        ],
    )
    def test_a_bad_request_is_a_400_that_names_the_field(
        self, api: APIClient, body: dict[str, Any], attr: str, code: str
    ) -> None:
        shop = Shop()

        response = reject(api, shop.cashier, shop.order, body)

        assert response.status_code == 400
        assert (first_error(response)["attr"], first_error(response)["code"]) == (
            attr,
            code,
        )
        assert Order.objects.get(pk=shop.order.pk).status == OrderStatus.PLACED
        assert results(shop.order) == []

    def test_a_note_of_200_characters_passes(self, api: APIClient) -> None:
        shop = Shop()

        response = reject(
            api,
            shop.cashier,
            shop.order,
            {"reason_code": "too_busy", "note": "x" * 200},
        )

        assert response.status_code == 200


class TestTheCustomerSeesTheAnswer:
    def test_the_message_the_order_and_the_conversation_follow_the_decision(
        self, api: APIClient
    ) -> None:
        shop = Shop()
        customer, customer_api = signed_in("sara-result@example.com")
        conversation = make_conversation(shop.restaurant, customer)
        order = make_order(conversation=conversation)
        before = customer_api.get(f"/api/v1/orders/{order.pk}").json()
        assert before["status"] == "placed"

        accept(api, shop.cashier, order, {"eta_minutes": 10})

        messages = customer_api.get(
            f"/api/v1/conversations/{conversation.pk}/messages"
        ).json()
        last = messages["messages"][-1]
        assert (last["sender"], last["kind"]) == ("bot", "result")
        assert last["payload"]["eta_minutes"] == 10
        assert messages["conversation"]["order"]["status"] == "accepted"
        detail = customer_api.get(f"/api/v1/orders/{order.pk}").json()
        assert detail["status"] == "accepted" and detail["eta_minutes"] == 10

    def test_a_rejection_shows_the_reason_on_the_customers_order(
        self, api: APIClient
    ) -> None:
        shop = Shop()
        customer, customer_api = signed_in("sara-reject@example.com")
        order = make_order(conversation=make_conversation(shop.restaurant, customer))

        reject(
            api,
            shop.cashier,
            order,
            {"reason_code": "other", "note": "Closed for prayer"},
        )

        detail = customer_api.get(f"/api/v1/orders/{order.pk}").json()
        assert detail["status"] == "rejected"
        assert detail["rejection_reason_code"] == "other"
        assert detail["rejection_note"] == "Closed for prayer"


class TestTheDecisionAndTheMessageAreOneStep:
    def test_when_the_message_cannot_be_posted_the_order_stays_placed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        shop = Shop()

        def broken(order: Order) -> None:
            raise RuntimeError("the chat is down")

        monkeypatch.setattr("orders.services.post_order_result", broken)

        with pytest.raises(RuntimeError):
            accept_order(
                order_id=shop.order.pk,
                restaurant=shop.restaurant,
                actor=shop.cashier.user,
                eta_minutes=10,
            )

        stored = Order.objects.get(pk=shop.order.pk)
        assert stored.status == OrderStatus.PLACED
        assert stored.eta_minutes is None
        assert not OrderEvent.objects.filter(
            order=shop.order, to_status="accepted"
        ).exists()


class TestWhoMayAnswer:
    def test_no_token_is_a_401(self, api: APIClient) -> None:
        shop = Shop()

        for action in ("accept", "reject"):
            response = api.post(
                f"/api/v1/staff/orders/{shop.order.pk}/{action}", {}, format="json"
            )

            assert response.status_code == 401

    def test_a_member_without_orders_decide_is_a_403_and_nothing_changes(
        self, api: APIClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        shop = Shop()
        monkeypatch.setitem(
            ROLE_PERMISSIONS, Role.CASHIER, frozenset({Permission.ORDERS_VIEW})
        )

        response = accept(api, shop.cashier, shop.order, {"eta_minutes": 10})

        assert response.status_code == 403
        assert Order.objects.get(pk=shop.order.pk).status == OrderStatus.PLACED
        assert results(shop.order) == []

    def test_an_admin_may_answer_too(self, api: APIClient) -> None:
        shop = Shop()
        admin = make_member(shop.restaurant, "cafe-one-admin", Role.ADMIN)

        response = reject(api, admin, shop.order, {"reason_code": "too_busy"})

        assert response.status_code == 200

    def test_a_customers_token_does_not_open_the_staff_endpoints(
        self, api: APIClient
    ) -> None:
        shop = Shop()
        _, customer_api = signed_in("sara-staff@example.com")

        response = customer_api.post(
            f"/api/v1/staff/orders/{shop.order.pk}/accept",
            {"eta_minutes": 10},
            format="json",
        )

        assert response.status_code in {401, 403}
        assert Order.objects.get(pk=shop.order.pk).status == OrderStatus.PLACED


class TestTenancy:
    def test_another_restaurants_order_is_a_404_and_stays_untouched(
        self, api: APIClient
    ) -> None:
        mine = Shop("cafe-one")
        theirs = Shop("cafe-two")

        accepted = accept(api, mine.cashier, theirs.order, {"eta_minutes": 10})
        rejected = reject(api, mine.cashier, theirs.order, {"reason_code": "too_busy"})

        assert accepted.status_code == 404
        assert rejected.status_code == 404
        assert Order.objects.get(pk=theirs.order.pk).status == OrderStatus.PLACED
        assert results(theirs.order) == []
        assert not OrderEvent.objects.filter(
            order=theirs.order, to_status__in=["accepted", "rejected"]
        ).exists()

    def test_an_unknown_order_is_a_404(self, api: APIClient) -> None:
        shop = Shop()

        response = api.post(
            "/api/v1/staff/orders/6f1c0f4e-5b0e-4a77-9a55-0d6d7a1f2b11/accept",
            {"eta_minutes": 10},
            format="json",
            headers=headers_of(shop.cashier),
        )

        assert response.status_code == 404

    def test_answering_one_restaurants_order_leaves_the_others_chats_alone(
        self, api: APIClient
    ) -> None:
        mine = Shop("cafe-one")
        theirs = Shop("cafe-two")

        accept(api, mine.cashier, mine.order, {"eta_minutes": 10})

        assert len(results(mine.order)) == 1
        assert results(theirs.order) == []
        assert Order.objects.get(pk=theirs.order.pk).status == OrderStatus.PLACED
