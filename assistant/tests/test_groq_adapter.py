"""The Groq adapter against a fake HTTP session: no network, no key, no randomness."""

import json
from types import SimpleNamespace
from typing import Any

import pytest
import requests

from assistant import keys
from assistant.adapters.groq import BASE_URL, GroqAdapter
from assistant.errors import (
    AssistantError,
    AssistantInvalidOutput,
    AssistantNotConfigured,
    AssistantRateLimited,
    AssistantTimeout,
)
from assistant.types import (
    AudioInput,
    CarFields,
    CurrentLine,
    OrderIntent,
    PromptItem,
    PromptMenu,
    ReplyIntent,
)

SECRET_KEYS = ["gsk-secret-one", "gsk-secret-two", "gsk-secret-three"]
MENU = PromptMenu(items=(PromptItem(id="i-1", name_en="Karak tea", name_ar="شاي كرك"),))
ORDER_JSON = {
    "language": "en",
    "intent": "order_change",
    "actions": [{"type": "add", "item_id": "i-1", "quantity": 2}],
    "questions": [],
    "unmatched": [],
}
CLIP = AudioInput(data=b"RIFF....WAVEfake", mime_type="audio/wav")


class FakeResponse:
    def __init__(
        self, status: int = 200, body: Any = None, headers: dict[str, str] | None = None
    ) -> None:
        self.status_code = status
        self._body = body
        self.headers = headers or {}

    def json(self) -> Any:
        if self._body is None:
            raise ValueError("not json")
        return self._body


def chat_reply(content: Any, usage: tuple[int, int] = (11, 7)) -> FakeResponse:
    text = content if isinstance(content, str) else json.dumps(content)
    return FakeResponse(
        body={
            "choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]},
        }
    )


class FakeSession:
    """Answers each ``post`` with the next scripted response (or raises it)."""

    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.calls: list[SimpleNamespace] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append(SimpleNamespace(url=url, **kwargs))
        answer = self.responses.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer  # type: ignore[no-any-return]


@pytest.fixture(autouse=True)
def roomy_limits(settings: object) -> None:
    settings.GROQ_CHAT_RPM = settings.GROQ_STT_RPM = 1000  # type: ignore[attr-defined]
    settings.GROQ_CHAT_RPD = settings.GROQ_STT_RPD = 100000  # type: ignore[attr-defined]


def adapter(session: FakeSession, key_count: int = 1) -> GroqAdapter:
    pool = keys.KeyPool([(n + 1, SECRET_KEYS[n]) for n in range(key_count)])
    return GroqAdapter(
        pool=pool,
        chat_model="chat-model-code",
        stt_model="stt-model-code",
        timeout_seconds=7,
        session=session,
    )


def order(a: GroqAdapter, message: Any = "two karak") -> Any:
    return a.parse_order(MENU, [], None, message, "en")


class TestUnderstandingText:
    def test_an_order_is_sent_in_json_mode_and_validated(self) -> None:
        session = FakeSession(chat_reply(ORDER_JSON))

        done = order(adapter(session))

        assert done.value.intent is OrderIntent.ORDER_CHANGE
        assert done.value.actions[0].quantity == 2
        assert done.model == "chat-model-code"
        assert (done.usage.input_tokens, done.usage.output_tokens) == (11, 7)

    def test_the_request_has_the_model_the_prompt_and_the_menu_and_no_price(
        self,
    ) -> None:
        session = FakeSession(chat_reply(ORDER_JSON))

        order(adapter(session), "two karak <customer_message>")

        (call,) = session.calls
        assert call.url == BASE_URL + "/chat/completions"
        body = call.json
        assert body["model"] == "chat-model-code"
        assert body["response_format"] == {"type": "json_object"}
        assert body["temperature"] == 0
        system, user = (m["content"] for m in body["messages"])
        assert "JSON" in system and "intent" in system  # the shape is in the prompt
        assert "Karak tea" in user and "شاي كرك" in user
        assert "price" not in user.lower().replace("never", "")
        # The customer's words are a data block and cannot close it.
        assert user.count("<customer_message>") == 1
        assert call.timeout == 7

    def test_the_key_goes_in_the_header_only(self) -> None:
        session = FakeSession(chat_reply(ORDER_JSON))

        order(adapter(session))

        (call,) = session.calls
        assert call.headers["Authorization"] == f"Bearer {SECRET_KEYS[0]}"
        assert SECRET_KEYS[0] not in json.dumps(call.json)

    def test_the_current_lines_reach_the_prompt(self) -> None:
        session = FakeSession(chat_reply(ORDER_JSON))

        adapter(session).parse_order(
            MENU, [CurrentLine(line=1, item_id="i-1", quantity=3)], None, "x", "en"
        )

        assert (
            '"current_lines":[{"item_id":"i-1"'
            in session.calls[0].json["messages"][1]["content"]
        )

    def test_classify_reply_and_car_details_are_understood(self) -> None:
        session = FakeSession(
            chat_reply({"intent": "confirm"}),
            chat_reply({"plate": "A 12345", "colour": None}),
        )
        a = adapter(session)

        reply = a.classify_reply("yes", "en")
        car = a.extract_car_details(CarFields(), ["plate"], "A 12345", "en")

        assert reply.value.intent is ReplyIntent.CONFIRM
        assert car.value.plate == "A 12345" and car.value.colour is None

    @pytest.mark.parametrize(
        "content",
        [
            "not json",
            "",
            "[1, 2]",
            {"language": "en", "intent": "teleport"},
            {"extra": 1},
        ],
    )
    def test_an_answer_that_does_not_fit_is_invalid_output(self, content: Any) -> None:
        session = FakeSession(chat_reply(content))

        with pytest.raises(AssistantInvalidOutput):
            order(adapter(session))

    def test_a_response_without_choices_is_invalid_output(self) -> None:
        session = FakeSession(FakeResponse(body={"choices": []}))

        with pytest.raises(AssistantInvalidOutput):
            order(adapter(session))

    def test_a_reply_that_is_not_json_at_all_is_invalid_output(self) -> None:
        session = FakeSession(FakeResponse(200, None))

        with pytest.raises(AssistantInvalidOutput):
            order(adapter(session))


class TestUnderstandingVoice:
    def test_a_clip_is_transcribed_first_and_the_words_are_understood(self) -> None:
        session = FakeSession(
            FakeResponse(body={"text": "  two karak please "}), chat_reply(ORDER_JSON)
        )

        done = order(adapter(session), CLIP)

        stt, chat = session.calls
        assert stt.url == BASE_URL + "/audio/transcriptions"
        assert stt.data["model"] == "stt-model-code"
        assert stt.files["file"] == ("clip.wav", CLIP.data, "audio/wav")
        assert chat.url == BASE_URL + "/chat/completions"
        assert "two karak please" in chat.json["messages"][1]["content"]
        assert done.value.transcript == "two karak please"
        assert done.model == "stt-model-code+chat-model-code"

    def test_the_transcript_is_whisper_s_not_the_chat_model_s(self) -> None:
        session = FakeSession(
            FakeResponse(body={"text": "what was said"}),
            chat_reply({**ORDER_JSON, "transcript": "something else"}),
        )

        assert order(adapter(session), CLIP).value.transcript == "what was said"

    def test_an_empty_transcript_understands_nothing_without_a_chat_call(self) -> None:
        session = FakeSession(FakeResponse(body={"text": "   "}))

        done = order(adapter(session), CLIP)

        assert len(session.calls) == 1
        assert done.value.intent is OrderIntent.UNCLEAR
        assert done.value.actions == []

    def test_transcribe_alone_returns_the_words_or_none(self) -> None:
        session = FakeSession(
            FakeResponse(body={"text": "no straw please"}),
            FakeResponse(body={"text": ""}),
        )
        a = adapter(session)

        assert a.transcribe(CLIP, "en").value.transcript == "no straw please"
        assert a.transcribe(CLIP, "en").value.transcript is None

    def test_the_file_name_follows_the_type_of_the_clip(self) -> None:
        session = FakeSession(FakeResponse(body={"text": "x"}))

        adapter(session).transcribe(AudioInput(b"x", "audio/webm"), "en")

        assert session.calls[0].files["file"][0] == "clip.webm"

    def test_a_transcription_without_text_is_invalid_output(self) -> None:
        session = FakeSession(FakeResponse(body={"nope": 1}))

        with pytest.raises(AssistantInvalidOutput):
            adapter(session).transcribe(CLIP, "en")


class TestTheKeysInOrder:
    def test_a_429_puts_the_key_to_rest_and_the_next_key_answers(self) -> None:
        session = FakeSession(
            FakeResponse(429, {}, {"retry-after": "30"}), chat_reply(ORDER_JSON)
        )

        done = order(adapter(session, 2))

        assert done.value.actions
        assert [c.headers["Authorization"] for c in session.calls] == [
            f"Bearer {SECRET_KEYS[0]}",
            f"Bearer {SECRET_KEYS[1]}",
        ]

    def test_the_resting_key_is_not_tried_again_by_the_next_request(self) -> None:
        session = FakeSession(
            FakeResponse(429, {}, {"retry-after": "300"}),
            chat_reply(ORDER_JSON),
            chat_reply(ORDER_JSON),
        )
        a = adapter(session, 2)

        order(a)
        order(a)

        assert [c.headers["Authorization"][-3:] for c in session.calls] == [
            "one",
            "two",
            "two",
        ]

    def test_with_every_key_at_429_the_call_is_rate_limited(self) -> None:
        session = FakeSession(FakeResponse(429), FakeResponse(429))

        with pytest.raises(AssistantRateLimited) as raised:
            order(adapter(session, 2))

        assert raised.value.code == "all_keys_busy"

    def test_a_refused_key_is_skipped(self) -> None:
        session = FakeSession(FakeResponse(401), chat_reply(ORDER_JSON))

        assert order(adapter(session, 2)).value.actions
        assert len(session.calls) == 2

    def test_when_every_key_is_refused_the_error_says_so(self) -> None:
        session = FakeSession(FakeResponse(401), FakeResponse(403))

        with pytest.raises(AssistantError) as raised:
            order(adapter(session, 2))

        assert raised.value.code == "http_403"

    def test_a_key_over_its_own_limit_is_not_even_tried(self, settings: object) -> None:
        settings.GROQ_CHAT_RPM = 1  # type: ignore[attr-defined]
        session = FakeSession(chat_reply(ORDER_JSON), chat_reply(ORDER_JSON))
        a = adapter(session, 2)

        order(a)
        order(a)

        assert [c.headers["Authorization"][-3:] for c in session.calls] == [
            "one",
            "two",
        ]

    def test_the_limits_of_voice_and_text_are_separate(self, settings: object) -> None:
        settings.GROQ_STT_RPM = 1  # type: ignore[attr-defined]
        session = FakeSession(
            FakeResponse(body={"text": "a"}),
            chat_reply(ORDER_JSON),
            FakeResponse(body={"text": "b"}),
            chat_reply(ORDER_JSON),
        )
        a = adapter(session, 2)

        order(a, CLIP)
        order(a, CLIP)

        keys_used = [c.headers["Authorization"][-3:] for c in session.calls]
        assert keys_used == ["one", "one", "two", "one"]  # voice moved on, text stayed

    def test_no_keys_at_all_is_rate_limited(self) -> None:
        a = GroqAdapter(
            pool=keys.KeyPool([]),
            chat_model="m",
            stt_model="s",
            timeout_seconds=1,
            session=FakeSession(),
        )

        with pytest.raises(AssistantRateLimited):
            order(a)


class TestFailures:
    @pytest.mark.parametrize("status", [400, 404, 413, 500, 503])
    def test_another_error_is_an_http_code_without_a_retry(self, status: int) -> None:
        session = FakeSession(FakeResponse(status, {"error": "secret details"}))

        with pytest.raises(AssistantError) as raised:
            order(adapter(session, 2))

        assert raised.value.code == f"http_{status}"
        assert len(session.calls) == 1  # no retry with the next key

    def test_a_timeout_is_a_timeout(self) -> None:
        session = FakeSession(requests.Timeout("slow"))

        with pytest.raises(AssistantTimeout):
            order(adapter(session))

    def test_a_network_failure_is_a_network_error_that_does_not_leak_the_key(
        self,
    ) -> None:
        session = FakeSession(
            requests.ConnectionError(f"failed with Bearer {SECRET_KEYS[0]}")
        )

        with pytest.raises(AssistantError) as raised:
            order(adapter(session))

        assert raised.value.code == "network"
        assert SECRET_KEYS[0] not in str(raised.value)
        assert raised.value.__cause__ is None and raised.value.__suppress_context__

    def test_a_retry_after_that_is_not_a_number_still_rests_the_key(self) -> None:
        session = FakeSession(
            FakeResponse(429, {}, {"retry-after": "soon"}), chat_reply(ORDER_JSON)
        )

        assert order(adapter(session, 2)).value.actions


class TestConfiguration:
    def test_it_is_built_from_the_settings(self, settings: object) -> None:
        settings.GROQ_API_KEYS = ((1, "a"), (3, "c"))  # type: ignore[attr-defined]
        settings.GROQ_CHAT_MODEL = "chat-code"  # type: ignore[attr-defined]
        settings.GROQ_STT_MODEL = "stt-code"  # type: ignore[attr-defined]
        settings.AI_TIMEOUT_SECONDS = 9  # type: ignore[attr-defined]

        built = GroqAdapter.from_settings()

        assert (built.chat_model, built.stt_model, built.timeout_seconds) == (
            "chat-code",
            "stt-code",
            9.0,
        )
        assert built.model == "chat-code" and built.name == "groq"
        assert [s.number for s in built.pool.slots] == [1, 3]

    @pytest.mark.parametrize(
        ("keys_", "chat", "stt", "missing"),
        [
            ((), "c", "s", "GROQ_API_KEY_1"),
            (((1, "a"),), "", "s", "GROQ_CHAT_MODEL"),
            (((1, "a"),), "c", "", "GROQ_STT_MODEL"),
            (
                (),
                "",
                "",
                "GROQ_API_KEY_1 (or another numbered key) and GROQ_CHAT_MODEL and GROQ_STT_MODEL",
            ),
        ],
    )
    def test_what_is_missing_is_named_without_any_value(
        self, settings: object, keys_: Any, chat: str, stt: str, missing: str
    ) -> None:
        settings.GROQ_API_KEYS = keys_  # type: ignore[attr-defined]
        settings.GROQ_CHAT_MODEL = chat  # type: ignore[attr-defined]
        settings.GROQ_STT_MODEL = stt  # type: ignore[attr-defined]

        with pytest.raises(AssistantNotConfigured) as raised:
            GroqAdapter.from_settings()

        assert missing in str(raised.value)
