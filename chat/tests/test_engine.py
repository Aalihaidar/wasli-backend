"""What the engine does with what the assistant understood: ordering, questions and repairs."""

import pytest

from assistant.types import (
    ActionType,
    OrderAction,
    OrderIntent,
)
from chat.models import Conversation
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
    which_burger,
)

pytestmark = pytest.mark.django_db


class TestChangingTheOrder:
    def test_adding_the_same_item_again_adds_to_its_quantity(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(
            monkeypatch,
            {
                parse("a karak"): understood(add(world.karak)),
                parse("another karak"): understood(add(world.karak, 2)),
            },
        )
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        say_text(api, conversation_id, "a karak")

        response = say_text(api, conversation_id, "another karak")

        lines = summary_of(response)["lines"]
        assert len(lines) == 1
        assert lines[0]["quantity"] == 3 and lines[0]["line_total_minor"] == 900

    def test_a_line_is_changed_by_its_number_and_the_numbers_stay_in_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(
            monkeypatch,
            {
                parse("two things"): understood(add(world.karak), add(world.sandwich)),
                parse("no karak, three sandwiches"): understood(
                    OrderAction(type=ActionType.REMOVE, line=1),
                    OrderAction(type=ActionType.SET_QUANTITY, line=1, quantity=3),
                ),
                parse("note"): understood(
                    OrderAction(type=ActionType.SET_NOTE, line=1, note="no onions")
                ),
            },
        )
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        say_text(api, conversation_id, "two things")

        changed = say_text(api, conversation_id, "no karak, three sandwiches")
        noted = say_text(api, conversation_id, "note")

        (line,) = summary_of(changed)["lines"]
        assert line["line"] == 1 and line["name"] == "Cheese sandwich"
        assert line["quantity"] == 3 and line["line_total_minor"] == 3600
        assert summary_of(noted)["lines"][0]["note"] == "no onions"

    def test_a_line_that_does_not_exist_changes_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(
            monkeypatch,
            {
                parse("karak"): understood(add(world.karak)),
                parse("remove nine"): understood(
                    OrderAction(type=ActionType.REMOVE, line=9)
                ),
            },
        )
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        say_text(api, conversation_id, "karak")

        response = say_text(api, conversation_id, "remove nine")

        assert bot_texts(response)[0].startswith("Sorry, I did not understand")
        assert len(summary_of(response)["lines"]) == 1

    def test_clear_and_cancel_empty_the_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(
            monkeypatch,
            {
                parse("karak"): understood(add(world.karak)),
                parse("forget it"): understood(intent=OrderIntent.CANCEL),
            },
        )
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        say_text(api, conversation_id, "karak")

        response = say_text(api, conversation_id, "forget it")

        assert bot_texts(response) == [
            "I cleared your order. What would you like to order?"
        ]
        assert Conversation.objects.get(pk=conversation_id).lines == []

    def test_a_clear_yes_moves_on_like_the_confirm_button(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(
            monkeypatch,
            {
                parse("karak"): understood(add(world.karak)),
                parse("yes please"): understood(intent=OrderIntent.CONFIRM),
            },
        )
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        say_text(api, conversation_id, "karak")

        response = say_text(api, conversation_id, "yes please")

        assert response.json()["conversation"]["state"] == "ask_car"

    def test_a_yes_with_nothing_ordered_asks_what_to_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_world()
        scripted(monkeypatch, {parse("yes"): understood(intent=OrderIntent.CONFIRM)})
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = say_text(api, conversation_id, "yes")

        assert bot_texts(response) == [
            "Your order is empty. What would you like to order?"
        ]

    def test_things_not_on_the_menu_are_named_at_most_three_and_cut_short(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        long_name = "x" * 100
        scripted(
            monkeypatch,
            {
                parse("many"): understood(
                    add(world.karak),
                    unmatched=("pizza", "  sushi  ", long_name, "fourth", ""),
                )
            },
        )
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = say_text(api, conversation_id, "many")

        first = bot_texts(response)[0]
        assert first == f"I could not find this on the menu: pizza, sushi, {'x' * 60}."
        assert "fourth" not in first
        assert summary_of(response)["lines"][0]["name"] == "Karak tea"

    def test_a_finished_item_is_not_added_and_the_customer_is_told(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(
            monkeypatch,
            {
                parse("karak and iced tea"): understood(
                    add(world.karak), add(world.finished)
                )
            },
        )
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = say_text(api, conversation_id, "karak and iced tea")

        assert bot_texts(response)[0] == "Not available right now: Iced tea."
        assert [line["name"] for line in summary_of(response)["lines"]] == ["Karak tea"]

    def test_only_a_finished_item_leaves_the_order_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(monkeypatch, {parse("iced tea"): understood(add(world.finished))})
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = say_text(api, conversation_id, "iced tea")

        assert bot_texts(response) == [
            "Not available right now: Iced tea.",
            "What would you like to order?",
        ]

    def test_an_item_that_became_unavailable_is_caught_at_confirm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(
            monkeypatch,
            {
                parse("karak and sandwich"): understood(
                    add(world.karak), add(world.sandwich)
                )
            },
        )
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        say_text(api, conversation_id, "karak and sandwich")
        world.sandwich.is_available = False
        world.sandwich.save()

        response = tap(api, conversation_id, "confirm")

        assert response.json()["conversation"]["state"] == "ordering"
        assert bot_texts(response)[0] == "Not available right now: Cheese sandwich."
        assert [line["name"] for line in summary_of(response)["lines"]] == ["Karak tea"]

    def test_an_item_in_a_hidden_category_cannot_be_ordered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(monkeypatch, {parse("karak"): understood(add(world.karak))})
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        world.drinks.is_active = False
        world.drinks.save()

        response = say_text(api, conversation_id, "karak")

        assert not [
            m for m in response.json()["messages"] if m["kind"] == "order_summary"
        ]
        assert Conversation.objects.get(pk=conversation_id).lines == []

    def test_a_restaurant_that_stops_taking_orders_says_so(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(monkeypatch, {parse("karak"): understood(add(world.karak))})
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        world.restaurant.is_active = False
        world.restaurant.save()

        response = say_text(api, conversation_id, "karak")

        assert response.status_code == 201
        assert bot_texts(response) == [
            "This restaurant is not taking orders right now."
        ]

    def test_an_order_cannot_have_more_than_twenty_different_items(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from menu.tests.factories import make_item

        world = make_world()
        extra = [make_item(world.drinks, f"Extra {n}", 100) for n in range(20)]
        scripted(
            monkeypatch,
            {
                parse("everything"): understood(
                    *(add(item) for item in extra), add(world.karak)
                )
            },
        )
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = say_text(api, conversation_id, "everything")

        assert bot_texts(response)[0] == "An order can have at most 20 different items."
        assert len(summary_of(response)["lines"]) == 20


class TestQuestions:
    def test_a_required_option_is_asked_and_the_answer_prices_the_line(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(monkeypatch, {parse("a latte"): understood(add(world.latte))})
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        asked = say_text(api, conversation_id, "a latte")

        question = [m for m in asked.json()["messages"] if m["sender"] == "bot"][-1]
        assert question["kind"] == "text"
        assert question["text"] == "Which Milk would you like for Latte?"
        assert question["payload"]["quick_replies"] == [
            {"label": "Oat", "action": "choose", "value": str(world.oat.pk)},
            {"label": "Whole", "action": "choose", "value": str(world.whole.pk)},
        ]
        assert not [m for m in asked.json()["messages"] if m["kind"] == "order_summary"]

        answered = tap(api, conversation_id, "choose", value=str(world.oat.pk))

        assert answered.json()["messages"][0]["text"] == "Oat"
        (line,) = summary_of(answered)["lines"]
        assert line["options"] == [
            {"id": str(world.oat.pk), "name": "Oat", "price_delta_minor": 200}
        ]
        assert line["unit_price_minor"] == 1200
        assert Conversation.objects.get(pk=conversation_id).pending_question is None

    def test_a_default_option_fills_a_required_group_without_asking(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        world.whole.is_default = True
        world.whole.save()
        scripted(monkeypatch, {parse("a latte"): understood(add(world.latte))})
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = say_text(api, conversation_id, "a latte")

        (line,) = summary_of(response)["lines"]
        assert [o["name"] for o in line["options"]] == ["Whole"]

    def test_the_option_the_customer_named_needs_no_question(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(
            monkeypatch,
            {parse("oat latte"): understood(add(world.latte, 1, (world.oat,)))},
        )
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = say_text(api, conversation_id, "oat latte")

        assert summary_of(response)["total_minor"] == 1200

    def test_an_option_that_is_finished_is_dropped_and_reported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        world.oat.is_available = False
        world.oat.save()
        scripted(
            monkeypatch,
            {parse("oat latte"): understood(add(world.latte, 1, (world.oat,)))},
        )
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = say_text(api, conversation_id, "oat latte")

        assert bot_texts(response)[0] == "Not available right now: Oat."
        # The line stays and the customer is asked for the other milk.
        assert "Which Milk" in bot_texts(response)[1]
        buttons = response.json()["messages"][-1]["payload"]["quick_replies"]
        assert [b["label"] for b in buttons] == ["Whole"]

    def test_confirm_asks_the_open_question_instead_of_moving_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(monkeypatch, {parse("a latte"): understood(add(world.latte))})
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        say_text(api, conversation_id, "a latte")

        response = tap(api, conversation_id, "confirm")

        assert response.json()["conversation"]["state"] == "ordering"
        assert "Which Milk" in bot_texts(response)[0]

    def test_an_answer_that_is_not_an_option_of_the_question_is_stale(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(monkeypatch, {parse("a latte"): understood(add(world.latte))})
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        say_text(api, conversation_id, "a latte")

        response = tap(api, conversation_id, "choose", value=str(world.karak.pk))

        assert "not available any more" in bot_texts(response)[0]
        # The line still needs its milk, so the question comes again.
        assert "Which Milk" in bot_texts(response)[1]
        assert Conversation.objects.get(pk=conversation_id).lines[0]["option_ids"] == []

    def test_a_choice_with_no_question_open_is_stale(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(monkeypatch, {parse("karak"): understood(add(world.karak))})
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        say_text(api, conversation_id, "karak")

        response = tap(api, conversation_id, "choose", value=str(world.sandwich.pk))

        assert "not available any more" in bot_texts(response)[0]
        assert len(summary_of(response)["lines"]) == 1

    def test_an_unclear_mention_asks_which_item_and_the_tap_adds_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(
            monkeypatch,
            {parse("a burger"): understood(questions=(which_burger(world),))},
        )
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        asked = say_text(api, conversation_id, "a burger")

        question = asked.json()["messages"][-1]
        assert question["text"] == "Which one do you mean by “burger”?"
        assert [b["label"] for b in question["payload"]["quick_replies"]] == [
            "Chicken burger",
            "Beef burger",
        ]

        answered = tap(api, conversation_id, "choose", value=str(world.beef.pk))

        assert answered.json()["messages"][0]["text"] == "Beef burger"
        assert [line["name"] for line in summary_of(answered)["lines"]] == [
            "Beef burger"
        ]

    def test_a_question_about_items_that_are_not_on_the_menu_is_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import uuid

        from assistant.types import OrderQuestion, QuestionKind

        make_world()
        bogus = OrderQuestion(
            kind=QuestionKind.CHOOSE_ITEM,
            mention="x",
            item_ids=[str(uuid.uuid4()), str(uuid.uuid4())],
        )
        scripted(monkeypatch, {parse("a thing"): understood(questions=(bogus,))})
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = say_text(api, conversation_id, "a thing")

        assert bot_texts(response)[0].startswith("Sorry, I did not understand")

    def test_the_assistant_is_told_about_an_open_question(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        adapter = scripted(
            monkeypatch,
            {parse("a burger"): understood(questions=(which_burger(world),))},
        )
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        say_text(api, conversation_id, "a burger")

        say_text(api, conversation_id, "the beef one")

        pending = adapter.calls[-1].args["pending_question"]
        assert pending["kind"] == "choose_item"
        assert set(pending["item_ids"]) == {str(world.chicken.pk), str(world.beef.pk)}


class TestTheItemPicker:
    def test_the_picker_replaces_the_whole_order_and_the_server_prices_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(monkeypatch, {parse("karak"): understood(add(world.karak))})
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        say_text(api, conversation_id, "karak")

        response = tap(
            api,
            conversation_id,
            "set_lines",
            lines=[
                {"item_id": str(world.sandwich.pk), "quantity": 2, "note": "toasted"},
                {
                    "item_id": str(world.latte.pk),
                    "quantity": 1,
                    "option_ids": [str(world.oat.pk)],
                },
            ],
        )

        assert response.json()["messages"][0]["text"] == "Items picked from the menu"
        summary = summary_of(response)
        assert [(x["name"], x["line_total_minor"]) for x in summary["lines"]] == [
            ("Cheese sandwich", 2400),
            ("Latte", 1200),
        ]
        assert summary["lines"][0]["note"] == "toasted"
        assert summary["total_minor"] == 3600

    def test_an_empty_picker_empties_the_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(monkeypatch, {parse("karak"): understood(add(world.karak))})
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        say_text(api, conversation_id, "karak")

        response = tap(api, conversation_id, "set_lines", lines=[])

        assert bot_texts(response) == [
            "Your order is empty. What would you like to order?"
        ]

    def test_the_picker_cannot_add_an_item_of_another_restaurant(self) -> None:
        make_world()
        other = make_world("cafe-two")
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = tap(
            api,
            conversation_id,
            "set_lines",
            lines=[{"item_id": str(other.karak.pk), "quantity": 1}],
        )

        assert response.status_code == 201
        assert Conversation.objects.get(pk=conversation_id).lines == []

    def test_the_picker_never_takes_a_price(self) -> None:
        world = make_world()
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = tap(
            api,
            conversation_id,
            "set_lines",
            lines=[
                {"item_id": str(world.karak.pk), "quantity": 1, "unit_price_minor": 1}
            ],
        )

        assert summary_of(response)["total_minor"] == 300

    def test_a_quantity_out_of_range_is_refused(self) -> None:
        world = make_world()
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        for quantity in (0, 21):
            response = tap(
                api,
                conversation_id,
                "set_lines",
                lines=[{"item_id": str(world.karak.pk), "quantity": quantity}],
            )
            assert response.status_code == 400
