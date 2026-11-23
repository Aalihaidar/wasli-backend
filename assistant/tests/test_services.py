"""The layer around the adapter: the caps, the call log and the failures."""

import logging
from typing import Any

import pytest
from django.forms.models import model_to_dict

from assistant import limits
from assistant.adapters.fake import FakeAdapter
from assistant.errors import (
    AssistantBudgetExceeded,
    AssistantError,
    AssistantInputError,
    AssistantInvalidOutput,
    AssistantNotConfigured,
    AssistantRateLimited,
    AssistantTimeout,
)
from assistant.models import AICallLog
from assistant.services import Assistant, check_message, get_adapter
from assistant.types import AudioInput, CarFields, PromptMenu
from chat.tests.factories import make_conversation
from restaurants.tests.factories import make_restaurant

pytestmark = pytest.mark.django_db

MENU = PromptMenu(items=())
SECRET = "my private order words 0501234567"


class TestCaps:
    def test_text_over_the_cap_is_refused_before_anything_is_sent(self) -> None:
        fake = FakeAdapter()

        with pytest.raises(AssistantInputError):
            Assistant(fake).classify_reply("x" * (limits.MAX_TEXT_CHARS + 1), "en")

        assert fake.calls == []
        assert not AICallLog.objects.exists()

    def test_text_at_the_cap_is_fine(self) -> None:
        check_message("x" * limits.MAX_TEXT_CHARS)

    @pytest.mark.parametrize(
        "audio",
        [
            AudioInput(b"", "audio/wav"),
            AudioInput(b"x" * (limits.MAX_AUDIO_BYTES + 1), "audio/wav"),
            AudioInput(b"x", "video/mp4"),
            AudioInput(b"x", "audio/mp4"),
        ],
    )
    def test_audio_that_is_empty_large_or_of_an_unknown_type_is_refused(
        self, audio: AudioInput
    ) -> None:
        with pytest.raises(AssistantInputError):
            check_message(audio)

    @pytest.mark.parametrize("mime", sorted(limits.ACCEPTED_AUDIO_TYPES))
    def test_every_accepted_type_passes(self, mime: str) -> None:
        check_message(AudioInput(b"x", mime))


class TestCallLog:
    def test_a_good_call_is_logged_with_its_purpose_and_no_content(self) -> None:
        Assistant(FakeAdapter.recorded()).extract_car_details(
            CarFields(), ["plate"], SECRET, "en"
        )

        [call] = AICallLog.objects.all()
        assert (call.provider, call.model, call.purpose) == (
            "fake",
            "fake",
            "extract_car",
        )
        assert (call.input_kind, call.outcome, call.error_code) == ("text", "ok", "")
        assert call.latency_ms >= 0

    def test_nothing_the_customer_said_reaches_the_log_row(self) -> None:
        Assistant(FakeAdapter.recorded()).classify_reply(SECRET, "en")

        row = model_to_dict(AICallLog.objects.get())
        assert SECRET not in " ".join(str(value) for value in row.values())
        assert "0501234567" not in " ".join(str(value) for value in row.values())

    def test_nothing_the_customer_said_reaches_the_python_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG):
            Assistant(FakeAdapter.recorded()).classify_reply(SECRET, "en")
            with pytest.raises(AssistantError):
                Assistant(FakeAdapter(fail_with=AssistantTimeout())).classify_reply(
                    SECRET, "en"
                )

        assert SECRET not in caplog.text

    def test_a_voice_call_is_logged_as_audio(self) -> None:
        Assistant(FakeAdapter.recorded()).transcribe(
            AudioInput(b"no straw please", "audio/wav"), "en"
        )

        assert AICallLog.objects.get().input_kind == "audio"

    def test_the_restaurant_and_conversation_are_recorded_when_given(self) -> None:
        conversation = make_conversation(make_restaurant("cafe-a"))

        Assistant(FakeAdapter.recorded()).parse_order(
            MENU,
            [],
            None,
            "hello",
            "en",
            restaurant=conversation.restaurant,
            conversation=conversation,
        )

        call = AICallLog.objects.get()
        assert call.restaurant == conversation.restaurant
        assert call.conversation == conversation
        assert call.purpose == "parse_order"

    def test_a_call_outside_a_conversation_has_neither(self) -> None:
        Assistant(FakeAdapter.recorded()).classify_reply("yes", "en")

        call = AICallLog.objects.get()
        assert call.restaurant is None and call.conversation is None

    def test_tokens_and_model_come_from_the_completion(self) -> None:
        from assistant.types import ClassifyReplyResult, Completion, ReplyIntent, Usage

        class Counting(FakeAdapter):
            def classify_reply(self, message: Any, locale: str) -> Any:
                return Completion(
                    ClassifyReplyResult(intent=ReplyIntent.CONFIRM),
                    model="some-model",
                    usage=Usage(input_tokens=120, output_tokens=15),
                )

        Assistant(Counting()).classify_reply("yes", "en")

        call = AICallLog.objects.get()
        assert (call.model, call.input_tokens, call.output_tokens) == (
            "some-model",
            120,
            15,
        )


class TestFailures:
    @pytest.mark.parametrize(
        ("error", "outcome", "code"),
        [
            (AssistantTimeout(), "timeout", "timeout"),
            (AssistantRateLimited(), "rate_limited", "rate_limited"),
            (AssistantInvalidOutput(), "invalid_output", "invalid_output"),
            (AssistantInvalidOutput("empty_output"), "invalid_output", "empty_output"),
            (AssistantError("http_503"), "error", "http_503"),
        ],
    )
    def test_a_failure_is_logged_with_its_outcome_and_raised(
        self, error: AssistantError, outcome: str, code: str
    ) -> None:
        with pytest.raises(type(error)):
            Assistant(FakeAdapter(fail_with=error)).classify_reply("yes", "en")

        call = AICallLog.objects.get()
        assert (call.outcome, call.error_code) == (outcome, code)
        assert call.input_tokens is None

    def test_an_unexpected_exception_becomes_a_provider_error_without_its_text(
        self,
    ) -> None:
        class Broken(FakeAdapter):
            def classify_reply(self, message: Any, locale: str) -> Any:
                raise RuntimeError(f"the provider echoed: {message}")

        with pytest.raises(AssistantError) as raised:
            Assistant(Broken()).classify_reply(SECRET, "en")

        assert SECRET not in str(raised.value)
        assert raised.value.__cause__ is None
        call = AICallLog.objects.get()
        assert (call.outcome, call.error_code) == ("error", "unexpected")
        assert SECRET not in str(model_to_dict(call))


class TestProviderChoice:
    def test_the_fake_provider_is_the_default_of_the_tests(self, settings: Any) -> None:
        settings.AI_PROVIDER = "fake"

        assert isinstance(get_adapter(), FakeAdapter)

    def test_gemini_without_its_key_or_model_stops_with_a_clear_message(
        self, settings: Any
    ) -> None:
        settings.AI_PROVIDER = "gemini"
        settings.GEMINI_API_KEY = ""
        settings.GEMINI_MODEL = "some-model"

        with pytest.raises(AssistantNotConfigured, match="GEMINI_API_KEY"):
            get_adapter()

        settings.GEMINI_API_KEY = "invented-key"
        settings.GEMINI_MODEL = ""
        with pytest.raises(AssistantNotConfigured, match="GEMINI_MODEL"):
            get_adapter()

    def test_the_adapter_is_made_on_first_use(self, settings: Any) -> None:
        settings.AI_PROVIDER = "gemini"
        settings.GEMINI_API_KEY = ""
        settings.GEMINI_MODEL = ""

        assistant = Assistant()  # nothing is read yet

        with pytest.raises(AssistantNotConfigured):
            assistant.classify_reply("yes", "en")


class TestGeminiBudget:
    def _gemini_fake(self) -> FakeAdapter:
        fake = FakeAdapter()
        fake.name = "gemini"
        return fake

    def test_a_call_over_the_daily_budget_is_refused_logged_and_never_sent(
        self, settings: Any
    ) -> None:
        settings.GEMINI_DAILY_REQUEST_LIMIT = 2
        fake = self._gemini_fake()
        assistant = Assistant(fake)
        assistant.classify_reply("yes", "en")
        assistant.classify_reply("yes", "en")

        with pytest.raises(AssistantBudgetExceeded) as raised:
            assistant.classify_reply("yes", "en")

        assert raised.value.code == "budget_exceeded"
        assert len(fake.calls) == 2
        assert AICallLog.objects.filter(outcome="budget_exceeded").count() == 1

    def test_the_refused_calls_do_not_use_up_the_budget_further(
        self, settings: Any
    ) -> None:
        settings.GEMINI_DAILY_REQUEST_LIMIT = 1
        assistant = Assistant(self._gemini_fake())
        assistant.classify_reply("yes", "en")

        for _ in range(3):
            with pytest.raises(AssistantBudgetExceeded):
                assistant.classify_reply("yes", "en")

        assert AICallLog.objects.filter(outcome="ok").count() == 1

    def test_another_provider_has_no_daily_budget_here(self, settings: Any) -> None:
        settings.GEMINI_DAILY_REQUEST_LIMIT = 0
        fake = FakeAdapter()  # named "fake"

        Assistant(fake).classify_reply("yes", "en")

        assert len(fake.calls) == 1


class TestChoosingTheProvider:
    def test_the_setting_chooses_and_an_argument_overrides_it(
        self, settings: Any
    ) -> None:
        settings.AI_PROVIDER = "fake"
        settings.GROQ_API_KEYS = ((1, "k"),)
        settings.GROQ_CHAT_MODEL = "c"
        settings.GROQ_STT_MODEL = "s"

        assert get_adapter().name == "fake"
        assert get_adapter("groq").name == "groq"

        settings.AI_PROVIDER = "groq"
        assert get_adapter().name == "groq"
        assert get_adapter("fake").name == "fake"

    def test_groq_without_its_settings_names_what_is_missing(
        self, settings: Any
    ) -> None:
        settings.AI_PROVIDER = "groq"
        settings.GROQ_API_KEYS = ()

        with pytest.raises(AssistantNotConfigured):
            get_adapter()
