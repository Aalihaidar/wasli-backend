"""The chat endpoints: opening a conversation, polling it and sending messages (issue #79)."""

import uuid
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from assistant.availability import FAILURE_WINDOW_SECONDS
from assistant.errors import (
    AssistantBudgetExceeded,
    AssistantInvalidOutput,
    AssistantTimeout,
)
from assistant.models import AICallLog
from chat.models import Conversation, ConversationState, Message
from chat.tests.helpers import (
    add,
    bot_texts,
    make_world,
    open_chat,
    parse,
    say_text,
    scripted,
    signed_in,
    summary_of,
    tap,
    understood,
)
from customers.tests.factories import make_customer
from orders.models import Order
from restaurants.models import RestaurantMenuImage

pytestmark = pytest.mark.django_db


def _messages_url(conversation_id: str) -> str:
    return f"/api/v1/conversations/{conversation_id}/messages"


class TestOpeningAConversation:
    def test_a_new_conversation_holds_the_welcome_the_menu_images_and_the_question(
        self,
    ) -> None:
        world = make_world()
        for number in (1, 2):
            RestaurantMenuImage.objects.create(
                restaurant=world.restaurant,
                image=f"restaurants/menu/{number}.jpg",
                caption_en=f"Page {number}",
                sort_order=number,
            )
        _, api = signed_in()

        response = open_chat(api, locale="en")

        assert response.status_code == 201
        body = response.json()
        assert body["conversation"]["restaurant_slug"] == "cafe-one"
        assert body["conversation"]["state"] == "ordering"
        assert body["conversation"]["locale"] == "en"
        assert body["conversation"]["order_type"] == "car"
        assert body["conversation"]["ai_available"] is True
        messages = body["messages"]
        assert [m["seq"] for m in messages] == [1, 2, 3, 4]
        assert [m["kind"] for m in messages] == ["text", "image", "image", "text"]
        assert messages[0]["text"] == "Welcome to Cafe One."
        assert messages[1]["text"] == "Page 1"
        assert messages[1]["image_url"].endswith("restaurants/menu/1.jpg")
        assert messages[1]["image_url"].startswith("http")
        assert messages[3]["text"] == "What would you like to order?"
        assert all(m["sender"] == "bot" and m["transcript"] is None for m in messages)

    def test_a_restaurant_without_menu_images_sends_no_image_message(self) -> None:
        make_world()
        _, api = signed_in()

        kinds = [m["kind"] for m in open_chat(api).json()["messages"]]

        assert kinds == ["text", "text"]

    def test_the_welcome_is_the_restaurants_own_text_when_it_has_one(self) -> None:
        make_world(welcome_message_en="Hello from us!")
        _, api = signed_in()

        english = open_chat(api, locale="en").json()["messages"][0]["text"]
        arabic = open_chat(api, locale="ar", start_new=True).json()["messages"][0][
            "text"
        ]

        assert english == "Hello from us!"
        assert (
            arabic == "Hello from us!"
        )  # no Arabic welcome: the English one stands in

    def test_the_bot_writes_in_arabic_when_asked(self) -> None:
        make_world()
        _, api = signed_in()

        texts = bot_texts(open_chat(api, locale="ar"))

        assert texts[-1] == "ماذا تريد أن تطلب؟"
        assert "مقهى" in texts[0] or "Cafe One" in texts[0]

    def test_the_language_defaults_to_the_customers_own(self) -> None:
        make_world()
        customer, api = signed_in()
        customer.locale = "ar"
        customer.save()

        assert open_chat(api).json()["conversation"]["locale"] == "ar"

    def test_the_same_conversation_comes_back_with_its_whole_history(self) -> None:
        make_world()
        _, api = signed_in()
        first = open_chat(api).json()

        again = open_chat(api)

        assert again.status_code == 200
        assert again.json()["conversation"]["id"] == first["conversation"]["id"]
        assert [m["seq"] for m in again.json()["messages"]] == [1, 2]
        assert Conversation.objects.count() == 1

    def test_start_new_makes_a_new_conversation(self) -> None:
        make_world()
        _, api = signed_in()
        first = open_chat(api).json()["conversation"]["id"]

        second = open_chat(api, start_new=True)

        assert second.status_code == 201
        assert second.json()["conversation"]["id"] != first
        assert [m["seq"] for m in second.json()["messages"]] == [1, 2]

    def test_an_expired_conversation_is_replaced(self) -> None:
        make_world()
        _, api = signed_in()
        first = open_chat(api).json()["conversation"]["id"]
        Conversation.objects.filter(pk=first).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        again = open_chat(api)

        assert again.status_code == 201
        assert again.json()["conversation"]["id"] != first

    def test_a_placed_conversation_stays_current_after_its_expiry(self) -> None:
        make_world()
        _, api = signed_in()
        first = open_chat(api).json()["conversation"]["id"]
        Conversation.objects.filter(pk=first).update(
            state=ConversationState.PLACED,
            expires_at=timezone.now() - timedelta(hours=1),
        )

        again = open_chat(api)

        assert again.status_code == 200
        assert again.json()["conversation"]["id"] == first
        assert again.json()["conversation"]["state"] == "placed"

    def test_each_customer_has_their_own_conversation(self) -> None:
        make_world()
        _, first_api = signed_in("a-chat@example.com")
        _, second_api = signed_in("b-chat@example.com")

        a = open_chat(first_api).json()["conversation"]["id"]
        b = open_chat(second_api).json()["conversation"]["id"]

        assert a != b

    def test_only_the_car_order_type_is_accepted(self) -> None:
        make_world()
        _, api = signed_in()

        response = open_chat(api, order_type="delivery")

        assert response.status_code == 400
        assert response.json()["errors"][0]["code"] == "unsupported_order_type"
        assert Conversation.objects.count() == 0

    def test_an_unknown_order_type_is_a_validation_error(self) -> None:
        make_world()
        _, api = signed_in()

        assert open_chat(api, order_type="teleport").status_code == 400

    def test_an_unknown_restaurant_is_a_404(self) -> None:
        _, api = signed_in()

        assert open_chat(api, slug="nowhere").status_code == 404

    def test_a_suspended_restaurant_is_a_404(self) -> None:
        make_world(subscription_status="suspended")
        _, api = signed_in()

        assert open_chat(api).status_code == 404

    def test_a_customer_token_is_required(self) -> None:
        make_world()

        response = APIClient().post(
            "/api/v1/restaurants/cafe-one/conversations", {}, format="json"
        )

        assert response.status_code == 401

    def test_the_response_is_never_cached(self) -> None:
        make_world()
        _, api = signed_in()

        assert open_chat(api)["Cache-Control"] == "no-store"


class TestReadingMessages:
    def test_after_seq_returns_only_newer_messages(self) -> None:
        make_world()
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        newer = api.get(_messages_url(conversation_id), {"after_seq": 1})
        everything = api.get(_messages_url(conversation_id))
        nothing = api.get(_messages_url(conversation_id), {"after_seq": 2})

        assert [m["seq"] for m in newer.json()["messages"]] == [2]
        assert [m["seq"] for m in everything.json()["messages"]] == [1, 2]
        assert nothing.json()["messages"] == []
        assert nothing.json()["conversation"]["id"] == conversation_id

    def test_a_bad_after_seq_is_a_validation_error(self) -> None:
        make_world()
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        assert (
            api.get(_messages_url(conversation_id), {"after_seq": -1}).status_code
            == 400
        )
        assert (
            api.get(_messages_url(conversation_id), {"after_seq": "x"}).status_code
            == 400
        )

    def test_another_customers_conversation_is_a_404(self) -> None:
        make_world()
        _, owner = signed_in("owner-chat@example.com")
        _, other = signed_in("other-chat@example.com")
        conversation_id = open_chat(owner).json()["conversation"]["id"]

        assert other.get(_messages_url(conversation_id)).status_code == 404
        assert say_text(other, conversation_id, "hello").status_code == 404
        assert tap(other, conversation_id, "confirm").status_code == 404
        assert Message.objects.filter(sender="customer").count() == 0

    def test_an_unknown_conversation_is_a_404(self) -> None:
        _, api = signed_in()

        response = api.get(_messages_url(str(uuid.uuid4())))

        assert response.status_code == 404
        assert response.json()["errors"][0]["code"] == "not_found"

    def test_an_expired_conversation_can_still_be_read(self) -> None:
        make_world()
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        Conversation.objects.filter(pk=conversation_id).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        assert api.get(_messages_url(conversation_id)).status_code == 200


class TestSendingText:
    def test_an_order_is_understood_and_summarised_with_prices(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(
            monkeypatch,
            {
                parse("two karak tea and one cheese sandwich"): understood(
                    add(world.karak, 2), add(world.sandwich)
                )
            },
        )
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = say_text(
            api, conversation_id, "two karak tea and one cheese sandwich"
        )

        assert response.status_code == 201
        messages = response.json()["messages"]
        assert [m["sender"] for m in messages] == ["customer", "bot"]
        assert messages[0]["text"] == "two karak tea and one cheese sandwich"
        assert messages[0]["used_voice"] is False and messages[0]["transcript"] is None
        assert messages[1]["kind"] == "order_summary"
        assert (
            messages[1]["text"] == "Do you confirm the order or do you want to edit it?"
        )
        assert messages[1]["payload"]["quick_replies"] == [
            {"label": "Confirm", "action": "confirm"},
            {"label": "Edit", "action": "edit"},
        ]
        summary = summary_of(response)
        assert summary["currency"] == "AED"
        assert summary["subtotal_minor"] == summary["total_minor"] == 1800
        assert summary["lines"][0] == {
            "line": 1,
            "item_id": str(world.karak.pk),
            "name": "Karak tea",
            "options": [],
            "quantity": 2,
            "note": None,
            "unit_price_minor": 300,
            "line_total_minor": 600,
        }
        assert summary["lines"][1]["line_total_minor"] == 1200

    def test_the_summary_is_written_in_the_conversations_language(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(monkeypatch, {parse("karak"): understood(add(world.karak))})
        _, api = signed_in()
        conversation_id = open_chat(api, locale="ar").json()["conversation"]["id"]

        response = say_text(api, conversation_id, "karak")

        assert summary_of(response)["lines"][0]["name"] == "شاي"
        assert bot_texts(response) == ["هل تؤكد الطلب أم تريد تعديله؟"]

    def test_the_assistant_gets_this_restaurants_menu_and_no_price(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        other = make_world("cafe-two")
        adapter = scripted(monkeypatch, {parse("karak"): understood(add(world.karak))})
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        say_text(api, conversation_id, "karak")

        (call,) = adapter.calls
        ids = {item.id for item in call.args["menu"].items}
        assert str(world.karak.pk) in ids
        assert str(other.karak.pk) not in ids

    def test_an_item_of_another_restaurant_is_dropped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        other = make_world("cafe-two")
        scripted(monkeypatch, {parse("sneaky"): understood(add(other.karak))})
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = say_text(api, conversation_id, "sneaky")

        assert Conversation.objects.get(pk=conversation_id).lines == []
        assert not [
            m for m in response.json()["messages"] if m["kind"] == "order_summary"
        ]
        assert world.restaurant.slug == "cafe-one"

    def test_an_unclear_message_gets_a_short_answer_and_changes_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_world()
        scripted(monkeypatch)
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = say_text(api, conversation_id, "mumble")

        assert bot_texts(response) == [
            "Sorry, I did not understand that. Please write what you would like to order.",
            "What would you like to order?",
        ]
        assert Conversation.objects.get(pk=conversation_id).lines == []

    def test_every_assistant_call_is_logged_without_its_content(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(monkeypatch, {parse("secret words"): understood(add(world.karak))})
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        say_text(api, conversation_id, "secret words")

        (log,) = AICallLog.objects.all()
        assert log.purpose == "parse_order"
        assert str(log.conversation_id) == conversation_id
        assert log.restaurant_id == world.restaurant.pk
        assert "secret" not in repr(log.__dict__)

    def test_a_repeated_client_message_id_returns_the_first_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        adapter = scripted(monkeypatch, {parse("karak"): understood(add(world.karak))})
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        same_id = uuid.uuid4()

        first = say_text(api, conversation_id, "karak", same_id)
        replay = say_text(api, conversation_id, "karak", same_id)

        assert replay.status_code == 201
        assert replay.json()["messages"] == first.json()["messages"]
        assert len(adapter.calls) == 1
        assert Message.objects.filter(client_message_id=same_id).count() == 1

    def test_a_replay_returns_only_its_own_replies(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(
            monkeypatch,
            {
                parse("karak"): understood(add(world.karak)),
                parse("sandwich"): understood(add(world.sandwich)),
            },
        )
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        first_id = uuid.uuid4()
        first = say_text(api, conversation_id, "karak", first_id)
        say_text(api, conversation_id, "sandwich")

        replay = say_text(api, conversation_id, "karak", first_id)

        assert replay.json()["messages"] == first.json()["messages"]

    def test_text_and_action_together_are_refused(self) -> None:
        make_world()
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = api.post(
            _messages_url(conversation_id),
            {"client_message_id": str(uuid.uuid4()), "text": "hi", "action": "confirm"},
            format="json",
        )

        assert response.status_code == 400

    def test_neither_text_nor_action_is_refused(self) -> None:
        make_world()
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = api.post(
            _messages_url(conversation_id),
            {"client_message_id": str(uuid.uuid4())},
            format="json",
        )

        assert response.status_code == 400

    def test_a_text_over_500_characters_is_refused(self) -> None:
        make_world()
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = say_text(api, conversation_id, "\u0627" * 501)

        assert response.status_code == 400
        error = response.json()["errors"][0]
        assert error["code"] == "max_length" and error["attr"] == "text"

    def test_500_characters_are_accepted_counted_as_code_points(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_world()
        scripted(monkeypatch)
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        assert say_text(api, conversation_id, "\u0627" * 500).status_code == 201
        assert (
            say_text(api, conversation_id, "  " + "a" * 500 + "  ").status_code == 201
        )

    def test_a_blank_text_is_refused(self) -> None:
        make_world()
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        assert say_text(api, conversation_id, "   ").status_code == 400

    def test_a_missing_client_message_id_is_refused(self) -> None:
        make_world()
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = api.post(
            _messages_url(conversation_id), {"text": "hi"}, format="json"
        )

        assert response.status_code == 400

    def test_an_expired_conversation_refuses_new_messages(self) -> None:
        make_world()
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        Conversation.objects.filter(pk=conversation_id).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        response = say_text(api, conversation_id, "hi")

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "conversation_expired"
        assert Message.objects.filter(sender="customer").count() == 0

    def test_a_placed_conversation_takes_no_more_input(self) -> None:
        make_world()
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        Conversation.objects.filter(pk=conversation_id).update(
            state=ConversationState.PLACED
        )

        for response in (
            say_text(api, conversation_id, "more"),
            tap(api, conversation_id, "restart"),
        ):
            assert response.status_code == 409
            assert response.json()["errors"][0]["code"] == "invalid_action_for_state"

    def test_a_message_moves_the_expiry_forward(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_world()
        scripted(monkeypatch)
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        Conversation.objects.filter(pk=conversation_id).update(
            expires_at=timezone.now() + timedelta(minutes=1)
        )

        say_text(api, conversation_id, "hi")

        left = Conversation.objects.get(pk=conversation_id).expires_at - timezone.now()
        assert left > timedelta(minutes=50)

    def test_messages_are_numbered_without_gaps(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(monkeypatch, {parse("karak"): understood(add(world.karak))})
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        say_text(api, conversation_id, "karak")
        tap(api, conversation_id, "edit")

        everything = api.get(_messages_url(conversation_id)).json()["messages"]

        assert [m["seq"] for m in everything] == list(range(1, len(everything) + 1))


class TestWhenTheAssistantFails:
    def test_a_provider_failure_is_answered_in_the_chat_and_turns_the_assistant_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_world()
        adapter = scripted(monkeypatch, fail_with=AssistantTimeout())
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        first = say_text(api, conversation_id, "karak")
        second = say_text(api, conversation_id, "karak again")

        assert first.status_code == second.status_code == 201
        assert "pick your items from the menu" in bot_texts(first)[0]
        assert first.json()["conversation"]["ai_available"] is False
        assert "pick your items from the menu" in bot_texts(second)[0]
        assert len(adapter.calls) == 1  # the second message never reached the provider
        (log,) = AICallLog.objects.all()
        assert log.outcome == "timeout"

    def test_the_assistant_comes_back_after_five_minutes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_world()
        scripted(monkeypatch, fail_with=AssistantTimeout())
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        say_text(api, conversation_id, "karak")
        assert FAILURE_WINDOW_SECONDS == 300

        cache.clear()  # what the cache does when the window ends

        assert (
            api.get(_messages_url(conversation_id)).json()["conversation"][
                "ai_available"
            ]
            is True
        )

    def test_an_unreadable_answer_does_not_turn_the_assistant_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_world()
        scripted(monkeypatch, fail_with=AssistantInvalidOutput())
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = say_text(api, conversation_id, "karak")

        assert bot_texts(response)[0].startswith("Sorry, I did not understand")
        assert response.json()["conversation"]["ai_available"] is True

    def test_a_used_up_budget_is_answered_in_the_chat_without_an_outage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_world()
        scripted(monkeypatch, fail_with=AssistantBudgetExceeded())
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = say_text(api, conversation_id, "karak")

        assert response.status_code == 201
        assert "pick your items from the menu" in bot_texts(response)[0]
        # Nothing failed at the provider, so no five-minute window was started.
        assert response.json()["conversation"]["ai_available"] is True

    def test_the_item_picker_still_works_while_the_assistant_is_down(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(monkeypatch, fail_with=AssistantTimeout())
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        say_text(api, conversation_id, "karak")

        response = tap(
            api,
            conversation_id,
            "set_lines",
            lines=[{"item_id": str(world.karak.pk), "quantity": 3}],
        )

        assert summary_of(response)["total_minor"] == 900


class TestButtons:
    def _with_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> tuple[APIClient, str, object]:
        world = make_world()
        scripted(monkeypatch, {parse("karak"): understood(add(world.karak))})
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        say_text(api, conversation_id, "karak")
        return api, conversation_id, world

    def test_confirm_moves_on_to_the_car_question(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, conversation_id, _ = self._with_order(monkeypatch)

        response = tap(api, conversation_id, "confirm")

        assert response.status_code == 201
        messages = response.json()["messages"]
        assert messages[0]["sender"] == "customer" and messages[0]["text"] == "Confirm"
        assert messages[0]["payload"] == {"action": "confirm"}
        assert "parking name" in messages[1]["text"]
        assert response.json()["conversation"]["state"] == "ask_car"
        assert Order.objects.count() == 0  # placing the order is a later step

    def test_confirm_with_an_empty_order_asks_what_to_order(self) -> None:
        make_world()
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = tap(api, conversation_id, "confirm")

        assert bot_texts(response) == [
            "Your order is empty. What would you like to order?"
        ]
        assert response.json()["conversation"]["state"] == "ordering"

    def test_edit_asks_what_to_change(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api, conversation_id, _ = self._with_order(monkeypatch)

        response = tap(api, conversation_id, "edit")

        assert bot_texts(response)[0].startswith(
            "Tell me what you would like to change"
        )
        assert response.json()["conversation"]["state"] == "ordering"

    def test_a_tapped_button_is_replayed_with_its_client_message_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, conversation_id, _ = self._with_order(monkeypatch)
        same_id = uuid.uuid4()

        first = tap(api, conversation_id, "confirm", same_id)
        replay = tap(api, conversation_id, "confirm", same_id)

        assert replay.json()["messages"] == first.json()["messages"]
        assert Message.objects.filter(client_message_id=same_id).count() == 1

    def test_an_action_that_needs_a_value_without_it_is_refused(self) -> None:
        make_world()
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        for action in ("choose", "set_lines", "set_locale", "edit_field"):
            assert tap(api, conversation_id, action).status_code == 400

    def test_an_unknown_action_is_refused(self) -> None:
        make_world()
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        assert tap(api, conversation_id, "explode").status_code == 400

    def test_steps_that_are_not_built_yet_are_a_409(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, conversation_id, _ = self._with_order(monkeypatch)

        edit_field = tap(api, conversation_id, "edit_field", field="car")
        skip = tap(api, conversation_id, "skip_note")

        for response in (edit_field, skip):
            assert response.status_code == 409
            assert response.json()["errors"][0]["code"] == "invalid_action_for_state"

    def test_after_the_car_question_only_a_language_change_and_a_restart_are_taken(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, conversation_id, _ = self._with_order(monkeypatch)
        tap(api, conversation_id, "confirm")

        assert say_text(api, conversation_id, "A 12345").status_code == 409
        assert tap(api, conversation_id, "confirm").status_code == 409
        assert tap(api, conversation_id, "edit").status_code == 409

        arabic = tap(api, conversation_id, "set_locale", locale="ar")
        assert arabic.status_code == 201
        assert arabic.json()["conversation"]["locale"] == "ar"
        assert "أين أوقفت" in bot_texts(arabic)[0]

        restart = tap(api, conversation_id, "restart")
        assert restart.json()["conversation"]["state"] == "ordering"
        assert Conversation.objects.get(pk=conversation_id).lines == []

    def test_set_locale_in_ordering_repeats_the_summary_in_the_new_language(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, conversation_id, _ = self._with_order(monkeypatch)

        response = tap(api, conversation_id, "set_locale", locale="ar")

        assert response.json()["conversation"]["locale"] == "ar"
        assert summary_of(response)["lines"][0]["name"] == "شاي"

    def test_restart_clears_the_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api, conversation_id, _ = self._with_order(monkeypatch)

        response = tap(api, conversation_id, "restart")

        assert bot_texts(response) == [
            "Let's start again. What would you like to order?"
        ]
        assert Conversation.objects.get(pk=conversation_id).lines == []


class TestThrottling:
    def test_messages_are_limited_per_customer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_world()
        scripted(monkeypatch)
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "chat_message", "2/min")
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        codes = [say_text(api, conversation_id, "hi").status_code for _ in range(3)]
        polling = api.get(_messages_url(conversation_id)).status_code

        assert codes == [201, 201, 429]
        assert polling == 200  # polling is not counted against the message limit

    def test_opening_conversations_is_limited(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_world()
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "chat_open", "1/hour")
        customer = make_customer("busy-chat@example.com")
        assert customer.pk
        _, api = signed_in("busy2-chat@example.com")

        codes = [open_chat(api).status_code for _ in range(2)]

        assert codes == [201, 429]
