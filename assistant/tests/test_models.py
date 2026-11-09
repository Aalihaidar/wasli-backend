import pytest
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError

from assistant.models import AICallLog, InputKind, Outcome, Purpose
from chat.tests.factories import make_conversation
from restaurants.tests.factories import make_restaurant

pytestmark = pytest.mark.django_db


def make_call(**extra: object) -> AICallLog:
    values: dict[str, object] = {
        "provider": "fake",
        "model": "fake-model",
        "purpose": Purpose.PARSE_ORDER,
        "input_kind": InputKind.TEXT,
        "outcome": Outcome.OK,
        "latency_ms": 420,
        **extra,
    }
    return AICallLog.objects.create(**values)


class TestAICallLog:
    def test_a_call_made_outside_a_conversation_needs_no_restaurant(self) -> None:
        call = make_call()

        assert call.restaurant is None
        assert call.conversation is None
        assert call.pk.version == 4
        assert str(call) == "fake parse_order ok"

    def test_it_keeps_the_facts_of_the_call(self) -> None:
        conversation = make_conversation()
        call = make_call(
            restaurant=conversation.restaurant,
            conversation=conversation,
            purpose=Purpose.EXTRACT_CAR,
            input_kind=InputKind.AUDIO,
            input_tokens=900,
            output_tokens=60,
            outcome=Outcome.TIMEOUT,
            error_code="timeout",
        )
        call.refresh_from_db()

        assert call.restaurant == conversation.restaurant
        assert (call.input_tokens, call.output_tokens) == (900, 60)
        assert call.error_code == "timeout"

    def test_the_purposes_the_spec_names_exist(self) -> None:
        assert {p.value for p in Purpose} == {
            "parse_order",
            "classify_reply",
            "extract_car",
            "transcribe",
            "menu_draft",
        }

    def test_the_outcomes_the_spec_names_exist(self) -> None:
        assert {o.value for o in Outcome} == {
            "ok",
            "invalid_output",
            "error",
            "timeout",
            "rate_limited",
            "budget_exceeded",
        }

    def test_the_choices_are_checked(self) -> None:
        call = make_call()
        call.purpose = "gossip"
        call.outcome = "great"
        call.input_kind = "video"

        with pytest.raises(ValidationError) as error:
            call.full_clean()
        assert {"purpose", "outcome", "input_kind"} <= set(error.value.message_dict)

    def test_it_never_holds_what_the_customer_said_or_the_provider_answered(
        self,
    ) -> None:
        names = {field.name for field in AICallLog._meta.get_fields()}

        forbidden = {
            "text",
            "content",
            "prompt",
            "response",
            "output",
            "transcript",
            "audio",
            "message",
            "phone",
            "email",
            "latitude",
            "longitude",
            "location",
        }
        assert not names & forbidden

    def test_a_deleted_test_conversation_keeps_its_calls(self) -> None:
        conversation = make_conversation()
        call = make_call(restaurant=conversation.restaurant, conversation=conversation)

        conversation.delete()
        call.refresh_from_db()

        assert call.conversation is None
        assert call.restaurant is not None

    def test_a_restaurant_with_calls_cannot_be_deleted(self) -> None:
        restaurant = make_restaurant("cafe-a")
        make_call(restaurant=restaurant)

        with pytest.raises(ProtectedError):
            restaurant.delete()

    def test_the_newest_call_comes_first(self) -> None:
        first = make_call(provider="one")
        second = make_call(provider="two")

        assert list(AICallLog.objects.all()) == [second, first]
