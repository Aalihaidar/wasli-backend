"""The car question one item at a time, while the assistant cannot read a free answer."""

import pytest
from django.core.cache import cache

from assistant.availability import record_failure
from assistant.errors import AssistantTimeout
from chat.models import Conversation
from chat.tests.helpers import (
    FULL_CAR,
    PARTIAL_CAR,
    Flow,
    at_car,
    at_review,
    bot_texts,
    last_bot,
    make_wav,
    say_text,
    say_voice,
    scripted,
    start,
    tap,
)
from chat.texts import say
from orders.models import Order

pytestmark = pytest.mark.django_db

INTRO = "I cannot read free answers right now, so I will ask you one thing at a time."
ASK_PARKING = (
    "Where are you parked? Type the parking name and where your car is. The restaurant "
    "may reject the order if it does not know where you are."
)
ASK_PLATE = "What is the car number?"
ASK_MODEL = "What is the car model?"
ASK_COLOUR = "What is the car colour?"


def _conversation(flow: Flow) -> Conversation:
    return Conversation.objects.get(pk=flow.cid)


def _down_at_car(monkeypatch: pytest.MonkeyPatch) -> Flow:
    """The assistant is already down when the customer confirms the order."""
    flow = start(monkeypatch)
    record_failure()
    tap(
        flow.api,
        flow.cid,
        "set_lines",
        lines=[{"item_id": str(flow.world.karak.pk), "quantity": 2}],
    )
    return flow


def _confirm_into_the_questions(flow: Flow) -> None:
    response = tap(flow.api, flow.cid, "confirm")
    assert response.json()["conversation"]["state"] == "ask_car"
    assert bot_texts(response)[-1] == f"{INTRO}\n{ASK_PARKING}"


def _answer_all_four(flow: Flow) -> None:
    say_text(flow.api, flow.cid, "Parking B2 near the lift")
    say_text(flow.api, flow.cid, "a 12345")
    say_text(flow.api, flow.cid, "Toyota Camry")
    response = say_text(flow.api, flow.cid, "White")
    assert response.json()["conversation"]["state"] == "ask_note"


class TestStartingTheQuestions:
    def test_confirming_while_the_assistant_is_down_asks_the_first_item(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = _down_at_car(monkeypatch)

        _confirm_into_the_questions(flow)

        assert _conversation(flow).pending_field == "parking_note"

    def test_the_assistant_failing_at_the_answer_starts_them_and_uses_nothing_typed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_car(monkeypatch)
        scripted(monkeypatch, fail_with=AssistantTimeout())

        response = say_text(flow.api, flow.cid, FULL_CAR)

        assert response.status_code == 201
        assert bot_texts(response) == [f"{INTRO}\n{ASK_PARKING}"]
        assert response.json()["conversation"]["ai_available"] is False
        assert response.json()["conversation"]["state"] == "ask_car"
        conversation = _conversation(flow)
        assert conversation.pending_field == "parking_note"
        # The message held several items, so none of it was stored as the first answer.
        assert conversation.parking_note == ""
        assert conversation.vehicle_plate == ""

    def test_what_the_assistant_already_read_is_kept_and_only_the_rest_is_asked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_car(monkeypatch)
        say_text(flow.api, flow.cid, PARTIAL_CAR)  # parking and colour are read
        record_failure()

        response = say_text(flow.api, flow.cid, "a toyota")

        assert bot_texts(response) == [f"{INTRO}\n{ASK_PLATE}"]
        assert _conversation(flow).pending_field == "plate"

        say_text(flow.api, flow.cid, "a 12345")
        response = say_text(flow.api, flow.cid, "Toyota Camry")

        conversation = _conversation(flow)
        assert response.json()["conversation"]["state"] == "ask_note"
        assert conversation.parking_note == "At the entrance"
        assert conversation.vehicle_colour == "Black"
        assert conversation.vehicle_model == "Toyota Camry"


class TestTheQuestions:
    def test_the_four_items_are_asked_one_at_a_time_and_then_the_note(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = _down_at_car(monkeypatch)
        _confirm_into_the_questions(flow)

        second = say_text(flow.api, flow.cid, "Parking B2 near the lift")
        third = say_text(flow.api, flow.cid, "a 12345")
        fourth = say_text(flow.api, flow.cid, "Toyota Camry")
        done = say_text(flow.api, flow.cid, "White")

        assert bot_texts(second) == [ASK_PLATE]
        assert bot_texts(third) == [ASK_MODEL]
        assert bot_texts(fourth) == [ASK_COLOUR]
        assert bot_texts(done) == ["Any note for the order? You can skip."]
        assert done.json()["conversation"]["state"] == "ask_note"
        conversation = _conversation(flow)
        assert conversation.parking_note == "Parking B2 near the lift"
        assert conversation.vehicle_plate == "A 12345"  # cleaned like any other answer
        assert conversation.vehicle_model == "Toyota Camry"
        assert conversation.vehicle_colour == "White"
        assert conversation.pending_field == ""

    def test_an_answer_that_does_not_fit_is_asked_again_with_a_hint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = _down_at_car(monkeypatch)
        _confirm_into_the_questions(flow)
        say_text(flow.api, flow.cid, "Parking B2 near the lift")

        response = say_text(flow.api, flow.cid, "x")

        assert bot_texts(response) == [
            f"That does not fit: Number must be between 2 and 12 characters. Please try again.\n{ASK_PLATE}"
        ]
        conversation = _conversation(flow)
        assert conversation.pending_field == "plate"
        assert conversation.vehicle_plate == ""
        assert response.json()["conversation"]["state"] == "ask_car"

        retry = say_text(flow.api, flow.cid, "a 12345")

        assert bot_texts(retry) == [ASK_MODEL]

    def test_a_spoken_answer_cannot_be_read_and_the_same_question_stays(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = _down_at_car(monkeypatch)
        adapter = scripted(monkeypatch, fail_with=AssistantTimeout())
        _confirm_into_the_questions(flow)

        response = say_voice(flow.api, flow.cid, make_wav())

        assert response.status_code == 201
        assert bot_texts(response) == [
            "I cannot understand voice messages right now. Please type your answer.",
            ASK_PARKING,
        ]
        assert response.json()["messages"][0]["transcript"] == ""
        assert _conversation(flow).pending_field == "parking_note"
        assert adapter.calls == []  # the clip never reached the assistant

    def test_a_voice_message_before_the_first_question_starts_them(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_car(monkeypatch)
        record_failure()

        response = say_voice(flow.api, flow.cid, make_wav())

        assert bot_texts(response) == [
            "I cannot understand voice messages right now. Please type your answer.",
            f"{INTRO}\n{ASK_PARKING}",
        ]
        assert _conversation(flow).pending_field == "parking_note"

    def test_a_conversation_that_has_started_finishes_even_when_the_assistant_is_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = _down_at_car(monkeypatch)
        _confirm_into_the_questions(flow)
        cache.clear()  # the assistant is available again

        response = say_text(flow.api, flow.cid, "Parking B2 near the lift")

        assert bot_texts(response) == [ASK_PLATE]
        assert flow.adapter.calls == []
        assert _conversation(flow).parking_note == "Parking B2 near the lift"

    def test_a_language_change_repeats_the_item_being_asked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = _down_at_car(monkeypatch)
        _confirm_into_the_questions(flow)
        say_text(flow.api, flow.cid, "Parking B2 near the lift")

        response = tap(flow.api, flow.cid, "set_locale", locale="ar")

        assert bot_texts(response) == [say("car_ask_plate", "ar")]
        assert _conversation(flow).pending_field == "plate"

    def test_a_restart_clears_the_questions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = _down_at_car(monkeypatch)
        _confirm_into_the_questions(flow)
        say_text(flow.api, flow.cid, "Parking B2 near the lift")

        response = tap(flow.api, flow.cid, "restart")

        conversation = _conversation(flow)
        assert response.json()["conversation"]["state"] == "ordering"
        assert conversation.pending_field == ""
        assert conversation.parking_note == ""

    def test_the_note_the_review_and_placing_work_after_the_questions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = _down_at_car(monkeypatch)
        _confirm_into_the_questions(flow)
        _answer_all_four(flow)

        note = say_text(flow.api, flow.cid, "No straw please")
        assert note.json()["conversation"]["state"] == "review"
        payload = last_bot(note)["payload"]
        assert payload["vehicle_plate"] == "A 12345"
        assert payload["parking_note"] == "Parking B2 near the lift"
        assert payload["order_note"] == "No straw please"

        placed = tap(flow.api, flow.cid, "confirm")

        assert placed.json()["conversation"]["state"] == "placed"
        order = Order.objects.get(conversation_id=flow.cid)
        assert order.vehicle_colour == "White"


class TestEditingTheCarFromTheReview:
    def test_all_four_are_asked_again_one_at_a_time_with_the_current_values(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)
        record_failure()

        shown = tap(flow.api, flow.cid, "edit_field", field="car")

        assert shown.json()["conversation"]["state"] == "ask_car"
        assert bot_texts(shown) == [
            f"{INTRO}\n{ASK_PARKING}\nNow: Parking B2 near the lift"
        ]

        second = say_text(flow.api, flow.cid, "Parking C1 by the gate")
        third = say_text(flow.api, flow.cid, "b 777")
        fourth = say_text(flow.api, flow.cid, "Nissan Patrol")
        done = say_text(flow.api, flow.cid, "Black")

        assert bot_texts(second) == [f"{ASK_PLATE}\nNow: A 12345"]
        assert bot_texts(third) == [f"{ASK_MODEL}\nNow: Toyota Camry"]
        assert bot_texts(fourth) == [f"{ASK_COLOUR}\nNow: White"]
        assert done.json()["conversation"]["state"] == "review"
        payload = last_bot(done)["payload"]
        assert payload["parking_note"] == "Parking C1 by the gate"
        assert payload["vehicle_plate"] == "B 777"
        assert payload["vehicle_model"] == "Nissan Patrol"
        assert payload["vehicle_colour"] == "Black"
        assert payload["order_note"] == "No straw please"  # the note is untouched
        assert _conversation(flow).pending_field == ""

    def test_a_car_edit_while_the_assistant_is_up_is_not_changed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flow = at_review(monkeypatch)

        shown = tap(flow.api, flow.cid, "edit_field", field="car")

        assert "This is what I have:" in bot_texts(shown)[0]
        assert _conversation(flow).pending_field == ""
