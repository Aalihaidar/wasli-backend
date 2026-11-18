import pytest

from assistant.adapters.fake import FakeAdapter
from assistant.errors import AssistantTimeout
from assistant.types import (
    AudioInput,
    CarFields,
    Language,
    OrderIntent,
    ParseOrderResult,
    PromptMenu,
    ReplyIntent,
)

MENU = PromptMenu(items=())


class TestRecordedOutputs:
    def test_the_english_car_answer_fills_all_four_fields(self) -> None:
        fake = FakeAdapter.recorded()

        result = fake.extract_car_details(
            CarFields(),
            [],
            "Parking B2 near the lift, plate A 12345, white Toyota Camry",
            "en",
        ).value

        assert (result.parking_note, result.plate, result.model, result.colour) == (
            "Parking B2 near the lift",
            "A 12345",
            "Toyota Camry",
            "White",
        )

    def test_a_partial_answer_fills_only_what_was_said(self) -> None:
        result = (
            FakeAdapter.recorded()
            .extract_car_details(
                CarFields(), [], "I'm at the entrance, the car is black", "en"
            )
            .value
        )

        assert result.parking_note == "At the entrance"
        assert result.colour == "Black"
        assert result.plate is None and result.model is None

    def test_the_arabic_car_answer_fills_all_four_fields(self) -> None:
        result = (
            FakeAdapter.recorded()
            .extract_car_details(
                CarFields(),
                [],
                "أنا في باركنغ B2 قرب المصعد، رقم السيارة A 12345، تويوتا كامري بيضاء",
                "ar",
            )
            .value
        )

        assert result.language is Language.AR
        assert result.plate == "A 12345" and result.colour == "بيضاء"

    def test_replies_are_classified(self) -> None:
        fake = FakeAdapter.recorded()

        assert (
            fake.classify_reply("Yes, send it", "en").value.intent
            is ReplyIntent.CONFIRM
        )
        edit = fake.classify_reply("change the note", "en").value
        assert edit.intent is ReplyIntent.EDIT and edit.field is not None
        assert fake.classify_reply("forget it", "en").value.intent is ReplyIntent.CANCEL

    def test_a_voice_note_is_transcribed_from_its_recorded_words(self) -> None:
        result = (
            FakeAdapter.recorded()
            .transcribe(AudioInput(b"no straw please", "audio/wav"), "en")
            .value
        )

        assert result.transcript == "No straw please"

    def test_an_unknown_message_gets_the_neutral_answer(self) -> None:
        fake = FakeAdapter.recorded()

        assert (
            fake.parse_order(MENU, [], None, "something new", "en").value.intent
            is OrderIntent.UNCLEAR
        )
        assert (
            fake.extract_car_details(CarFields(), [], "blah", "en").value.plate is None
        )
        assert fake.classify_reply("hmm", "en").value.intent is ReplyIntent.UNCLEAR
        assert (
            fake.transcribe(AudioInput(b"?", "audio/wav"), "en").value.transcript
            is None
        )


class TestScripts:
    def test_a_test_scripts_the_answer_it_needs(self) -> None:
        wanted = ParseOrderResult(language=Language.EN, intent=OrderIntent.CANCEL)
        fake = FakeAdapter({("parse_order", "Cancel it"): wanted})

        assert fake.parse_order(MENU, [], None, "  cancel IT ", "en").value is wanted

    def test_a_script_may_build_its_answer_from_the_call(self) -> None:
        def answer(lines: list[object], **_: object) -> ParseOrderResult:
            return ParseOrderResult(
                language=Language.EN,
                intent=OrderIntent.UNCLEAR if not lines else OrderIntent.CONFIRM,
            )

        fake = FakeAdapter({("parse_order", "yes"): answer})

        assert (
            fake.parse_order(MENU, [], None, "yes", "en").value.intent
            is OrderIntent.UNCLEAR
        )

    def test_calls_are_recorded_for_assertions(self) -> None:
        fake = FakeAdapter()

        fake.classify_reply("hello", "ar")

        [call] = fake.calls
        assert (call.purpose, call.message, call.locale) == (
            "classify_reply",
            "hello",
            "ar",
        )

    def test_a_failure_can_be_injected_to_test_the_fallbacks(self) -> None:
        fake = FakeAdapter(fail_with=AssistantTimeout())

        with pytest.raises(AssistantTimeout):
            fake.classify_reply("yes", "en")
        assert len(fake.calls) == 1

    def test_the_fake_reports_itself_as_the_provider(self) -> None:
        completion = FakeAdapter().classify_reply("x", "en")

        assert FakeAdapter.name == "fake" and completion.model == "fake"
