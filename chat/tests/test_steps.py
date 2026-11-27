"""The steps after ordering: the car, the note, the review and the placed order."""

import uuid

import pytest
from django.utils import timezone
from rest_framework.response import Response

from assistant.errors import AssistantTimeout
from assistant.types import (
    CarDetailsResult,
    ClassifyReplyResult,
    Language,
    ReplyField,
    ReplyIntent,
)
from chat.models import Conversation, Message
from chat.tests.helpers import (
    FULL_CAR,
    PARTIAL_CAR,
    Flow,
    at_car,
    at_note,
    at_review,
    bot_texts,
    hears,
    last_bot,
    make_wav,
    put_location,
    say_text,
    say_voice,
    scripted,
    summary_of,
    tap,
)
from customers.models import Vehicle
from orders.models import Order, OrderItem

pytestmark = pytest.mark.django_db

STILL_NEED = "Thank you. I still need {}."
PLATE = "the car number"
MODEL = "the car model"
COLOUR = "the car colour"
PARKING = "where your car is (the parking name and the spot)"


def _conversation(flow: Flow) -> Conversation:
    return Conversation.objects.get(pk=flow.cid)


class TestTheCarQuestion:
    def test_one_answer_with_everything_moves_on_to_the_note(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_car(monkeypatch)

        response = say_text(flow.api, flow.cid, FULL_CAR)

        assert response.status_code == 201
        assert response.json()["conversation"]["state"] == "ask_note"
        assert bot_texts(response) == ["Any note for the order? You can skip."]
        assert last_bot(response)["payload"]["quick_replies"] == [
            {"label": "Skip", "action": "skip_note"}
        ]
        conversation = _conversation(flow)
        assert conversation.parking_note == "Parking B2 near the lift"
        assert conversation.vehicle_plate == "A 12345"
        assert conversation.vehicle_model == "Toyota Camry"
        assert conversation.vehicle_colour == "White"

    def test_the_car_question_is_asked_once_in_full(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_car(monkeypatch)

        text = bot_texts(tap(flow.api, flow.cid, "set_locale", locale="en"))[0]

        assert text.startswith("Where are you parked?")
        assert "the parking name and where your car is" in text

    def test_a_partial_answer_then_only_the_missing_items_are_asked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_car(monkeypatch)

        first = say_text(flow.api, flow.cid, PARTIAL_CAR)

        assert first.json()["conversation"]["state"] == "ask_car"
        assert bot_texts(first) == [STILL_NEED.format(f"{PLATE}, {MODEL}")]
        conversation = _conversation(flow)
        assert conversation.parking_note == "At the entrance"
        assert (
            conversation.vehicle_colour == "Black" and conversation.vehicle_plate == ""
        )

        second = say_text(flow.api, flow.cid, FULL_CAR)

        assert second.json()["conversation"]["state"] == "ask_note"
        # Merge only: what the second answer said replaces, the rest is kept.
        assert _conversation(flow).vehicle_plate == "A 12345"

    def test_the_assistant_is_asked_only_for_what_is_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_car(monkeypatch)
        say_text(flow.api, flow.cid, PARTIAL_CAR)

        say_text(flow.api, flow.cid, "a toyota")

        asked = [
            c.args["asked"]
            for c in flow.adapter.calls
            if c.purpose == "extract_car_details"
        ]
        assert asked == [
            ["parking_note", "plate", "model", "colour"],
            ["plate", "model"],
        ]

    def test_an_answer_that_fails_the_rules_counts_as_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_car(
            monkeypatch,
            {
                ("extract_car_details", "short plate"): CarDetailsResult(
                    parking_note="Lot 3 by the gate",
                    plate="7",
                    model="Camry",
                    colour="Red",
                )
            },
        )

        response = say_text(flow.api, flow.cid, "short plate")

        assert bot_texts(response) == [STILL_NEED.format(PLATE)]
        assert _conversation(flow).vehicle_plate == ""

    def test_an_answer_with_nothing_in_it_asks_for_everything_again(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_car(monkeypatch)

        response = say_text(flow.api, flow.cid, "hmm")

        assert bot_texts(response)[0].startswith("I did not catch that. I still need ")
        for label in (PARKING, PLATE, MODEL, COLOUR):
            assert label in bot_texts(response)[0]

    def test_the_plate_is_stored_trimmed_upper_case_with_one_space(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_car(
            monkeypatch,
            {
                ("extract_car_details", "messy"): CarDetailsResult(
                    parking_note="Lot 3 by the gate",
                    plate="  a   12345 ",
                    model="Camry",
                    colour="Red",
                )
            },
        )

        say_text(flow.api, flow.cid, "messy")

        assert _conversation(flow).vehicle_plate == "A 12345"

    def test_the_questions_are_in_the_conversations_language(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_car(monkeypatch)
        tap(flow.api, flow.cid, "set_locale", locale="ar")

        response = say_text(flow.api, flow.cid, PARTIAL_CAR)

        assert "رقم السيارة" in bot_texts(response)[0]

    def test_a_language_change_repeats_the_question_in_the_new_language(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_car(monkeypatch)

        response = tap(flow.api, flow.cid, "set_locale", locale="ar")

        assert "أين أوقفت" in bot_texts(response)[0]
        assert response.json()["conversation"]["state"] == "ask_car"

    def test_a_spoken_answer_is_understood_and_its_words_kept(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_car(monkeypatch)
        hears(
            monkeypatch,
            "by the lift, A 12345, white Camry",
            parking_note="By the lift",
            plate="A 12345",
            model="Camry",
            colour="White",
        )

        response = say_voice(flow.api, flow.cid, make_wav())

        customer = response.json()["messages"][0]
        assert customer["used_voice"] is True
        assert customer["transcript"] == "by the lift, A 12345, white Camry"
        assert response.json()["conversation"]["state"] == "ask_note"

    def test_a_spoken_answer_with_no_words_is_asked_again(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_car(monkeypatch)
        hears(monkeypatch, None)

        response = say_voice(flow.api, flow.cid, make_wav())

        assert bot_texts(response)[0].startswith("Sorry, I could not hear")
        assert response.json()["messages"][0]["transcript"] == ""
        assert response.json()["conversation"]["state"] == "ask_car"

    def test_while_the_assistant_is_down_the_bot_asks_one_item_at_a_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_car(monkeypatch)
        scripted(monkeypatch, fail_with=AssistantTimeout())

        response = say_text(flow.api, flow.cid, FULL_CAR)

        assert response.status_code == 201
        assert "I cannot read free answers right now" in bot_texts(response)[0]
        assert response.json()["conversation"]["ai_available"] is False
        assert response.json()["conversation"]["state"] == "ask_car"
        # The details are in tests/test_car_fallback.py; nothing was stored from the message.
        assert _conversation(flow).vehicle_plate == ""

    def test_buttons_of_other_steps_are_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_car(monkeypatch)

        for action in ("confirm", "edit", "skip_note", "edit_field", "set_lines"):
            response = tap(flow.api, flow.cid, action, field="car", lines=[])
            assert response.status_code == 409, action
            assert response.json()["errors"][0]["code"] == "invalid_action_for_state"

    def test_restart_goes_back_to_an_empty_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_note(monkeypatch)

        response = tap(flow.api, flow.cid, "restart")

        assert response.json()["conversation"]["state"] == "ordering"
        conversation = _conversation(flow)
        assert conversation.lines == [] and conversation.vehicle_plate == ""
        assert conversation.parking_note == "" and conversation.order_note == ""


class TestTheNote:
    def test_a_note_is_kept_as_typed_and_leads_to_the_review(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_note(monkeypatch)

        response = say_text(flow.api, flow.cid, "  No   straw\nplease ")

        assert response.json()["conversation"]["state"] == "review"
        assert _conversation(flow).order_note == "No straw please"
        assert last_bot(response)["kind"] == "review"

    def test_skip_means_no_note(self, monkeypatch: pytest.MonkeyPatch) -> None:
        flow = at_note(monkeypatch)

        response = tap(flow.api, flow.cid, "skip_note")

        assert response.json()["messages"][0]["text"] == "Skip"
        assert response.json()["conversation"]["state"] == "review"
        assert _conversation(flow).order_note == ""
        assert last_bot(response)["payload"]["order_note"] == ""

    def test_a_note_is_not_read_by_the_assistant(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_note(monkeypatch)
        before = len(flow.adapter.calls)

        say_text(flow.api, flow.cid, "No onions")

        assert len(flow.adapter.calls) == before

    def test_a_note_over_300_characters_is_refused_in_the_chat(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_note(monkeypatch)

        response = say_text(flow.api, flow.cid, "x" * 301)

        assert bot_texts(response) == [
            "A note can have at most 300 characters. Please make it shorter."
        ]
        assert response.json()["conversation"]["state"] == "ask_note"

    def test_exactly_300_characters_are_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_note(monkeypatch)

        response = say_text(flow.api, flow.cid, "x" * 300)

        assert response.json()["conversation"]["state"] == "review"

    def test_a_spoken_note_is_transcribed_and_kept(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_note(monkeypatch)
        hears(monkeypatch, "No straw please")

        response = say_voice(flow.api, flow.cid, make_wav())

        customer = response.json()["messages"][0]
        assert customer["transcript"] == "No straw please"
        assert _conversation(flow).order_note == "No straw please"
        assert response.json()["conversation"]["state"] == "review"

    def test_a_spoken_note_with_no_words_is_asked_again(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_note(monkeypatch)
        hears(monkeypatch, None)

        response = say_voice(flow.api, flow.cid, make_wav())

        assert bot_texts(response)[0].startswith("Sorry, I could not hear")
        assert response.json()["conversation"]["state"] == "ask_note"

    def test_only_a_skip_and_the_language_and_restart_buttons_work_here(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_note(monkeypatch)

        assert tap(flow.api, flow.cid, "confirm").status_code == 409
        assert tap(flow.api, flow.cid, "edit_field", field="note").status_code == 409
        arabic = tap(flow.api, flow.cid, "set_locale", locale="ar")
        assert arabic.status_code == 201 and "ملاحظة" in bot_texts(arabic)[0]


class TestTheReview:
    def test_the_review_holds_the_order_the_car_the_note_and_the_buttons(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_note(monkeypatch)

        response = say_text(flow.api, flow.cid, "No straw please")

        message = last_bot(response)
        assert message["kind"] == "review"
        assert message["text"] == "Shall I send the order to the restaurant?"
        payload = message["payload"]
        assert payload["summary"]["total_minor"] == 600
        assert payload["summary"]["lines"][0]["quantity"] == 2
        assert payload["parking_note"] == "Parking B2 near the lift"
        assert payload["vehicle_plate"] == "A 12345"
        assert payload["vehicle_model"] == "Toyota Camry"
        assert payload["vehicle_colour"] == "White"
        assert payload["order_note"] == "No straw please"
        assert payload["location_shared"] is False
        assert payload["location_source"] == "none"
        assert payload["quick_replies"] == [
            {"label": "Yes, send", "action": "confirm"},
            {"label": "Edit", "action": "edit"},
        ]

    def test_the_review_says_whether_the_position_was_shared_but_never_its_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)
        put_location(flow.api, flow.cid, 25.2005, 55.2705, source="simulated")

        response = tap(flow.api, flow.cid, "set_locale", locale="en")

        payload = last_bot(response)["payload"]
        assert payload["location_shared"] is True
        assert payload["location_source"] == "simulated"
        assert "25.2005" not in response.content.decode()
        assert "55.2705" not in response.content.decode()

    def test_a_language_change_repeats_the_review(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)

        response = tap(flow.api, flow.cid, "set_locale", locale="ar")

        assert last_bot(response)["kind"] == "review"
        assert "هل أرسل" in last_bot(response)["text"]

    def test_edit_offers_the_three_parts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        flow = at_review(monkeypatch)

        response = tap(flow.api, flow.cid, "edit")

        assert response.json()["conversation"]["state"] == "review"
        assert last_bot(response)["payload"]["quick_replies"] == [
            {"label": "Order", "action": "edit_field", "field": "items"},
            {"label": "Car and parking", "action": "edit_field", "field": "car"},
            {"label": "Note", "action": "edit_field", "field": "note"},
        ]

    def test_editing_the_order_returns_to_the_review_at_the_next_confirm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)

        edit = tap(flow.api, flow.cid, "edit_field", field="items")
        assert edit.json()["conversation"]["state"] == "ordering"
        assert edit.json()["messages"][0]["text"] == "Order"
        assert summary_of(edit)["lines"][0]["quantity"] == 2
        changed = tap(
            flow.api,
            flow.cid,
            "set_lines",
            lines=[{"item_id": str(flow.world.sandwich.pk), "quantity": 1}],
        )
        assert summary_of(changed)["total_minor"] == 1200

        confirm = tap(flow.api, flow.cid, "confirm")

        assert confirm.json()["conversation"]["state"] == "review"
        assert last_bot(confirm)["payload"]["summary"]["total_minor"] == 1200
        assert last_bot(confirm)["payload"]["vehicle_plate"] == "A 12345"  # kept

    def test_editing_the_car_shows_the_values_and_changes_only_what_is_said(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(
            monkeypatch,
            {
                ("extract_car_details", "the colour is black"): CarDetailsResult(
                    colour="Black"
                ),
            },
        )

        shown = tap(flow.api, flow.cid, "edit_field", field="car")
        assert shown.json()["conversation"]["state"] == "ask_car"
        assert "This is what I have:" in bot_texts(shown)[0]
        assert "Number: A 12345" in bot_texts(shown)[0]
        assert "Tell me what to change." in bot_texts(shown)[0]

        response = say_text(flow.api, flow.cid, "the colour is black")

        assert response.json()["conversation"]["state"] == "review"
        payload = last_bot(response)["payload"]
        assert payload["vehicle_colour"] == "Black"
        assert payload["vehicle_plate"] == "A 12345"
        assert payload["parking_note"] == "Parking B2 near the lift"

    def test_an_edit_that_changes_nothing_is_said_and_asked_again(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)
        tap(flow.api, flow.cid, "edit_field", field="car")

        response = say_text(flow.api, flow.cid, "hmm")

        assert (
            bot_texts(response)[0]
            == "I did not catch a change. Tell me what to change."
        )
        assert response.json()["conversation"]["state"] == "ask_car"

    def test_editing_the_note_shows_it_and_the_answer_replaces_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)

        shown = tap(flow.api, flow.cid, "edit_field", field="note")
        assert "Your note is: “No straw please”" in bot_texts(shown)[0]
        assert last_bot(shown)["payload"]["quick_replies"] == [
            {"label": "Keep", "action": "skip_note"}
        ]

        response = say_text(flow.api, flow.cid, "Extra napkins")

        assert response.json()["conversation"]["state"] == "review"
        assert last_bot(response)["payload"]["order_note"] == "Extra napkins"

    def test_keep_leaves_the_note_as_it_is(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)
        tap(flow.api, flow.cid, "edit_field", field="note")

        response = tap(flow.api, flow.cid, "skip_note")

        assert response.json()["conversation"]["state"] == "review"
        assert last_bot(response)["payload"]["order_note"] == "No straw please"

    def test_a_free_text_edit_of_the_note_opens_the_note_step(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)

        response = say_text(flow.api, flow.cid, "change the note")

        assert response.json()["conversation"]["state"] == "ask_note"
        assert "Your note is:" in bot_texts(response)[0]

    def test_a_free_text_edit_that_holds_the_change_is_not_asked_twice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(
            monkeypatch,
            {
                ("classify_reply", "make the colour black"): ClassifyReplyResult(
                    language=Language.EN, intent=ReplyIntent.EDIT, field=ReplyField.CAR
                ),
                ("extract_car_details", "make the colour black"): CarDetailsResult(
                    colour="Black"
                ),
            },
        )

        response = say_text(flow.api, flow.cid, "make the colour black")

        assert response.json()["conversation"]["state"] == "review"
        assert last_bot(response)["payload"]["vehicle_colour"] == "Black"
        calls = [c.purpose for c in flow.adapter.calls][-2:]
        assert calls == [
            "classify_reply",
            "extract_car_details",
        ]  # two calls, as the spec allows

    def test_an_edit_without_a_part_offers_the_three_parts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(
            monkeypatch,
            {
                ("classify_reply", "i want to change something"): ClassifyReplyResult(
                    language=Language.EN, intent=ReplyIntent.EDIT
                )
            },
        )

        response = say_text(flow.api, flow.cid, "I want to change something")

        assert len(last_bot(response)["payload"]["quick_replies"]) == 3

    def test_a_cancel_clears_the_order_the_car_and_the_note(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)

        response = say_text(flow.api, flow.cid, "forget it")

        assert bot_texts(response) == [
            "I cleared your order. What would you like to order?"
        ]
        conversation = _conversation(flow)
        assert conversation.state == "ordering" and conversation.lines == []
        assert conversation.vehicle_plate == "" and conversation.order_note == ""

    def test_an_unclear_reply_asks_again_with_the_buttons(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)

        response = say_text(flow.api, flow.cid, "banana")

        assert bot_texts(response)[0].startswith("Sorry, I did not understand")
        assert last_bot(response)["kind"] == "review"
        assert response.json()["conversation"]["state"] == "review"

    def test_while_the_assistant_is_down_free_text_is_not_read_but_the_buttons_work(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)
        scripted(monkeypatch, fail_with=AssistantTimeout())

        response = say_text(flow.api, flow.cid, "yes send it")

        assert "Sorry" not in bot_texts(response)[0]
        assert (
            last_bot(response)["kind"] == "review"
        )  # the buttons are still the latest message
        assert last_bot(response)["payload"]["quick_replies"][0]["action"] == "confirm"
        assert (
            tap(flow.api, flow.cid, "confirm").json()["conversation"]["state"]
            == "placed"
        )

    def test_a_spoken_yes_places_the_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)
        hears(monkeypatch, "yes send it")

        response = say_voice(flow.api, flow.cid, make_wav())

        assert response.json()["messages"][0]["transcript"] == "yes send it"
        assert response.json()["conversation"]["state"] == "placed"
        assert Order.objects.count() == 1

    def test_an_item_that_went_unavailable_sends_the_customer_back_to_the_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)
        flow.world.karak.is_available = False
        flow.world.karak.save()

        response = tap(flow.api, flow.cid, "confirm")

        assert response.status_code == 201
        assert response.json()["conversation"]["state"] == "ordering"
        assert bot_texts(response)[0] == "Not available right now: Karak tea."
        assert Order.objects.count() == 0
        assert _conversation(flow).return_to_review is True


class TestPlacingTheOrder:
    def test_confirm_places_the_order_with_everything_copied(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)
        put_location(flow.api, flow.cid, 25.2005, 55.2705, accuracy_m=12)

        response = tap(flow.api, flow.cid, "confirm")

        assert response.status_code == 201
        assert response.json()["messages"][0]["text"] == "Yes, send"
        assert bot_texts(response) == [
            "Your order #1 was sent. Waiting for the restaurant to confirm."
        ]
        conversation = response.json()["conversation"]
        assert conversation["state"] == "placed"
        order = Order.objects.get()
        assert conversation["order"] == {
            "id": str(order.pk),
            "number": 1,
            "status": "placed",
        }
        assert (order.vehicle_plate, order.vehicle_model, order.vehicle_colour) == (
            "A 12345",
            "Toyota Camry",
            "White",
        )
        assert order.parking_note == "Parking B2 near the lift"
        assert order.customer_note == "No straw please"
        assert order.total_minor == 600 and order.order_type == "car"
        assert order.customer_lat == pytest.approx(25.2005)
        assert order.location_source == "gps" and order.distance_m is not None
        (item,) = OrderItem.objects.all()
        assert (item.name_en, item.quantity, item.line_total_minor) == (
            "Karak tea",
            2,
            600,
        )
        vehicle = Vehicle.objects.get(customer=flow.customer)
        assert vehicle.plate == "A 12345"

    def test_the_conversation_has_no_order_until_it_is_placed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)

        before = flow.api.get(f"/api/v1/conversations/{flow.cid}/messages")
        assert "order" not in before.json()["conversation"]

        tap(flow.api, flow.cid, "confirm")
        after = flow.api.get(f"/api/v1/conversations/{flow.cid}/messages")
        assert after.json()["conversation"]["order"]["number"] == 1
        assert after.json()["conversation"]["state"] == "placed"

    def test_a_spoken_or_typed_yes_places_it_too(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)

        response = say_text(flow.api, flow.cid, "yes, send it")

        assert response.json()["conversation"]["state"] == "placed"
        assert Order.objects.count() == 1

    def test_a_replayed_confirm_returns_the_first_result_and_places_one_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)
        same = uuid.uuid4()

        first = tap(flow.api, flow.cid, "confirm", same)
        again = tap(flow.api, flow.cid, "confirm", same)

        assert again.status_code == 201
        assert again.json()["messages"] == first.json()["messages"]
        assert Order.objects.count() == 1
        assert Message.objects.filter(client_message_id=same).count() == 1

    def test_a_placed_conversation_takes_nothing_more(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)
        tap(flow.api, flow.cid, "confirm")

        for response in (
            tap(flow.api, flow.cid, "confirm"),
            say_text(flow.api, flow.cid, "one more"),
            tap(flow.api, flow.cid, "restart"),
            put_location(flow.api, flow.cid),
        ):
            assert response.status_code == 409
            assert response.json()["errors"][0]["code"] == "invalid_action_for_state"
        assert Order.objects.count() == 1

    def test_the_next_order_of_the_restaurant_takes_the_next_number(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)
        tap(flow.api, flow.cid, "confirm")

        again = tap_new_order(flow)

        assert Order.objects.order_by("number").last().number == 2  # type: ignore[union-attr]
        assert again.json()["conversation"]["order"]["number"] == 2

    def test_a_phone_that_must_be_verified_refuses_the_order_and_stores_nothing(
        self, monkeypatch: pytest.MonkeyPatch, settings: object
    ) -> None:
        flow = at_review(monkeypatch)
        settings.REQUIRE_VERIFIED_PHONE = True  # type: ignore[attr-defined]
        messages_before = Message.objects.filter(conversation_id=flow.cid).count()
        restaurant = flow.world.restaurant
        restaurant.refresh_from_db()
        number_before = restaurant.next_order_number

        response = tap(flow.api, flow.cid, "confirm")

        assert response.status_code == 403
        assert response.json()["errors"][0]["code"] == "phone_not_verified"
        assert (
            Message.objects.filter(conversation_id=flow.cid).count() == messages_before
        )
        assert _conversation(flow).state == "review"
        assert Order.objects.count() == 0
        restaurant.refresh_from_db()
        assert restaurant.next_order_number == number_before

        # Once the phone is verified, the same conversation goes through.
        flow.customer.user.phone_verified_at = timezone.now()
        flow.customer.user.save()
        assert (
            tap(flow.api, flow.cid, "confirm").json()["conversation"]["state"]
            == "placed"
        )

    def test_a_far_order_is_refused_in_the_chat_only_when_the_location_check_enforces(
        self, monkeypatch: pytest.MonkeyPatch, settings: object
    ) -> None:
        flow = at_review(monkeypatch, service_radius_m=100)
        put_location(flow.api, flow.cid, 25.30, 55.30)  # kilometres away
        settings.LOCATION_CHECK = "enforce"  # type: ignore[attr-defined]

        response = tap(flow.api, flow.cid, "confirm")

        assert response.status_code == 201
        assert "outside the area this restaurant serves" in bot_texts(response)[0]
        assert last_bot(response)["kind"] == "review"
        assert Order.objects.count() == 0

        settings.LOCATION_CHECK = "warn"  # type: ignore[attr-defined]
        placed = tap(flow.api, flow.cid, "confirm")
        assert placed.json()["conversation"]["state"] == "placed"
        assert (Order.objects.get().distance_m or 0) > 100

    def test_an_order_without_a_position_is_placed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)

        tap(flow.api, flow.cid, "confirm")

        order = Order.objects.get()
        assert order.customer_lat is None and order.location_source == "none"

    def test_a_restaurant_that_stopped_taking_orders_says_so(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)
        flow.world.restaurant.is_active = False
        flow.world.restaurant.save()

        response = tap(flow.api, flow.cid, "confirm")

        assert bot_texts(response) == [
            "This restaurant is not taking orders right now."
        ]
        assert Order.objects.count() == 0


def tap_new_order(flow: Flow) -> Response:
    """A second order of the same restaurant, from a second conversation of the customer."""
    from chat.tests.helpers import open_chat

    second = open_chat(flow.api, start_new=True).json()["conversation"]["id"]
    tap(
        flow.api,
        second,
        "set_lines",
        lines=[{"item_id": str(flow.world.sandwich.pk), "quantity": 1}],
    )
    tap(flow.api, second, "confirm")
    say_text(flow.api, second, FULL_CAR)
    say_text(flow.api, second, "no note")
    return tap(flow.api, second, "confirm")
