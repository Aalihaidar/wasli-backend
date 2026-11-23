"""The Groq adapter: Whisper for voice, a text model to understand.

Groq serves open models through an OpenAI-style API. A voice note is two requests: Whisper turns
the clip into text (the audio is sent and dropped, never stored), then the chat model understands
the text. The model codes are settings (``GROQ_CHAT_MODEL``, ``GROQ_STT_MODEL``), never written
here. The chat answer is requested in JSON mode with the JSON shape in the prompt, and then
validated again with the pydantic models of ``assistant.types``; anything that does not fit is
``invalid_output``. No automatic retry of a failed call: a customer is waiting.

Several keys are used in order (``assistant.keys``). A key that is at its limit, or that Groq
answers ``429`` for, is skipped and the next one is tried within the same request; when no key is
left the call fails as ``rate_limited``. A key never appears in an error, a log or the call log.
"""

import json
from functools import cache
from typing import Any, TypeVar

import requests
from django.conf import settings
from pydantic import BaseModel, ValidationError

from assistant import keys, prompts
from assistant.errors import (
    AssistantError,
    AssistantInvalidOutput,
    AssistantNotConfigured,
    AssistantRateLimited,
    AssistantTimeout,
)
from assistant.types import (
    AudioInput,
    CarDetailsResult,
    CarFields,
    ClassifyReplyResult,
    Completion,
    CurrentLine,
    MessageInput,
    ParseOrderResult,
    PromptMenu,
    TranscribeResult,
    Usage,
)

from .base import AssistantAdapter
from .schemas import (
    CAR_DETAILS_SCHEMA,
    CLASSIFY_REPLY_SCHEMA,
    PARSE_ORDER_SCHEMA,
)

_T = TypeVar("_T", bound=BaseModel)

BASE_URL = "https://api.groq.com/openai/v1"
USER_AGENT = "wasli-backend/1.0"
# The longest a key is left alone after a "too many requests" answer, and the shortest.
MAX_REST_SECONDS = 24 * 3600
DEFAULT_REST_SECONDS = 60
# The answer is JSON only, but a reasoning model also spends tokens thinking.
MAX_COMPLETION_TOKENS = 4096

# The file name tells Whisper the format of the clip.
_AUDIO_FILE_NAMES = {
    "audio/wav": "clip.wav",
    "audio/x-wav": "clip.wav",
    "audio/mpeg": "clip.mp3",
    "audio/mp3": "clip.mp3",
    "audio/aac": "clip.aac",
    "audio/ogg": "clip.ogg",
    "audio/opus": "clip.opus",
    "audio/flac": "clip.flac",
    "audio/webm": "clip.webm",
}

# What a call returns when the clip had no words in it: the same as "understood nothing".
_NOTHING_HEARD: dict[type[BaseModel], dict[str, Any]] = {
    ParseOrderResult: {"language": "en", "intent": "unclear"},
    ClassifyReplyResult: {"intent": "unclear"},
    CarDetailsResult: {},
}


class GroqAdapter(AssistantAdapter):
    name = "groq"

    def __init__(
        self,
        *,
        pool: keys.KeyPool,
        chat_model: str,
        stt_model: str,
        timeout_seconds: float,
        session: Any = None,
    ) -> None:
        self.pool = pool
        self.chat_model = chat_model
        self.stt_model = stt_model
        self.timeout_seconds = timeout_seconds
        self.session = session or _session()

    @property
    def model(self) -> str:
        return self.chat_model

    @classmethod
    def from_settings(cls) -> GroqAdapter:
        """The adapter for the numbered ``GROQ_API_KEY_<n>`` keys and the two model codes."""
        missing = [
            name
            for name, present in (
                ("GROQ_API_KEY_1 (or another numbered key)", settings.GROQ_API_KEYS),
                ("GROQ_CHAT_MODEL", settings.GROQ_CHAT_MODEL),
                ("GROQ_STT_MODEL", settings.GROQ_STT_MODEL),
            )
            if not present
        ]
        if missing:
            raise AssistantNotConfigured(
                "AI_PROVIDER=groq needs " + " and ".join(missing) + "."
            )
        return cls(
            pool=keys.KeyPool.from_settings(),
            chat_model=settings.GROQ_CHAT_MODEL,
            stt_model=settings.GROQ_STT_MODEL,
            timeout_seconds=float(settings.AI_TIMEOUT_SECONDS),
        )

    # --- the four calls ---------------------------------------------------------------------

    def parse_order(
        self,
        menu: PromptMenu,
        lines: list[CurrentLine],
        pending_question: dict[str, Any] | None,
        message: MessageInput,
        locale: str,
    ) -> Completion[ParseOrderResult]:
        request = prompts.parse_order_request(
            menu, lines, pending_question, message, locale
        )
        return self._understand(request, PARSE_ORDER_SCHEMA, ParseOrderResult)

    def classify_reply(
        self, message: MessageInput, locale: str
    ) -> Completion[ClassifyReplyResult]:
        request = prompts.classify_reply_request(message, locale)
        return self._understand(request, CLASSIFY_REPLY_SCHEMA, ClassifyReplyResult)

    def extract_car_details(
        self,
        current: CarFields,
        asked: list[str],
        message: MessageInput,
        locale: str,
    ) -> Completion[CarDetailsResult]:
        request = prompts.extract_car_request(current, asked, message, locale)
        return self._understand(request, CAR_DETAILS_SCHEMA, CarDetailsResult)

    def transcribe(
        self, audio: AudioInput, locale_hint: str
    ) -> Completion[TranscribeResult]:
        text = self._speech_to_text(audio)
        return Completion(
            TranscribeResult(transcript=text or None), model=self.stt_model
        )

    # --- understanding ----------------------------------------------------------------------

    def _understand(
        self,
        request: prompts.PromptRequest,
        schema: dict[str, Any],
        result_type: type[_T],
    ) -> Completion[_T]:
        """Whisper first when the message is a voice note, then the chat model on the text."""
        message = request.message
        spoken = ""
        model = self.chat_model
        if isinstance(message, AudioInput):
            spoken = self._speech_to_text(message)
            model = f"{self.stt_model}+{self.chat_model}"
            if not spoken:
                return Completion(
                    result_type.model_validate(_NOTHING_HEARD[result_type]), model=model
                )
            message = spoken

        system = (
            request.system
            + "\nAnswer with one JSON object and nothing else. It must follow this JSON "
            "schema; a property marked nullable may be null, and every required property "
            "must be present:\n" + json.dumps(schema, ensure_ascii=False)
        )
        user = f"Context (JSON):\n{request.context}\n\n{prompts.message_text(message)}"
        body = self._post(
            keys.CHAT,
            "/chat/completions",
            json_body={
                "model": self.chat_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0,
                "max_completion_tokens": MAX_COMPLETION_TOKENS,
                "reasoning_effort": "low",
                "response_format": {"type": "json_object"},
            },
        )
        value = self._validated(body, result_type)
        if spoken and hasattr(value, "transcript"):
            # What was heard is what Whisper wrote, not what the chat model repeated.
            value = value.model_copy(update={"transcript": spoken})
        return Completion(value, model=model, usage=_usage(body))

    @staticmethod
    def _validated(body: dict[str, Any], result_type: type[_T]) -> _T:
        try:
            text = body["choices"][0]["message"]["content"]
        except KeyError, IndexError, TypeError:
            raise AssistantInvalidOutput("empty_output") from None
        if not isinstance(text, str) or not text.strip():
            raise AssistantInvalidOutput("empty_output")
        try:
            return result_type.model_validate(json.loads(text))
        except ValueError, ValidationError:
            # The text is never kept or logged.
            raise AssistantInvalidOutput from None

    # --- speech to text ---------------------------------------------------------------------

    def _speech_to_text(self, audio: AudioInput) -> str:
        """The words in a clip, or an empty string when there are none. The clip is sent and
        dropped."""
        name = _AUDIO_FILE_NAMES.get(audio.mime_type, "clip.wav")
        body = self._post(
            keys.STT,
            "/audio/transcriptions",
            data={
                "model": self.stt_model,
                "response_format": "json",
                "temperature": "0",
            },
            files={"file": (name, audio.data, audio.mime_type)},
        )
        text = body.get("text")
        if not isinstance(text, str):
            raise AssistantInvalidOutput("empty_output")
        return text.strip()

    # --- the request, with the keys in order ------------------------------------------------

    def _post(
        self,
        kind: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> dict[str, Any]:
        tried: set[int] = set()
        refused: int | None = None
        while True:
            slot = self.pool.take(kind, frozenset(tried))
            if slot is None:
                if refused is not None and len(tried) == len(self.pool.slots):
                    # Every key was refused, none was merely busy: the keys are wrong.
                    raise AssistantError(f"http_{refused}")
                raise AssistantRateLimited("all_keys_busy")
            tried.add(slot.number)
            try:
                response = self.session.post(
                    BASE_URL + path,
                    headers={
                        "Authorization": f"Bearer {slot.key}",
                        "User-Agent": USER_AGENT,
                    },
                    json=json_body,
                    data=data,
                    files=files,
                    timeout=self.timeout_seconds,
                )
            except requests.Timeout:
                raise AssistantTimeout from None
            except requests.RequestException:
                raise AssistantError("network") from None

            status = response.status_code
            if status == 429:
                self.pool.rest(kind, slot, _retry_after(response))
                refused = None
                continue
            if status in {401, 403}:
                self.pool.rest(kind, slot, keys.REFUSED_REST_SECONDS)
                refused = status
                continue
            if status >= 400:
                raise AssistantError(f"http_{status}")
            try:
                parsed = response.json()
            except ValueError:
                raise AssistantInvalidOutput("bad_json") from None
            if not isinstance(parsed, dict):
                raise AssistantInvalidOutput("bad_json")
            return parsed


def _retry_after(response: Any) -> int:
    """How long Groq asked the key to wait, in seconds (a minute when it did not say)."""
    try:
        seconds = int(float(response.headers.get("retry-after", DEFAULT_REST_SECONDS)))
    except TypeError, ValueError:
        seconds = DEFAULT_REST_SECONDS
    return min(max(seconds, 1), MAX_REST_SECONDS)


def _usage(body: dict[str, Any]) -> Usage:
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return Usage()
    return Usage(
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
    )


@cache
def _session() -> requests.Session:
    return requests.Session()
