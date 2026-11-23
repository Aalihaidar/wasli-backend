"""The Gemini adapter (Google AI Studio key, ``google-genai``).

Gemini takes audio directly, so a voice note is one request, not a speech-to-text step plus a
second one. The model name is a setting (``GEMINI_MODEL``), never written here: Google renames
and retires models. Every answer is requested in JSON schema mode and then validated again with
the pydantic models of ``assistant.types``; anything that does not fit is ``invalid_output``.
No automatic retry: a customer is waiting.
"""

import json
from functools import cache
from typing import Any, TypeVar

from django.conf import settings
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel, ValidationError

from assistant import prompts
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
    TRANSCRIBE_SCHEMA,
)

_T = TypeVar("_T", bound=BaseModel)


class GeminiAdapter(AssistantAdapter):
    name = "gemini"

    def __init__(
        self,
        *,
        client: Any,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self.client = client
        self.model = model
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_settings(cls) -> GeminiAdapter:
        """The adapter for ``GEMINI_API_KEY`` and ``GEMINI_MODEL``; the client is made once."""
        key, model = settings.GEMINI_API_KEY, settings.GEMINI_MODEL
        if not key or not model:
            missing = [
                name
                for name, value in (("GEMINI_API_KEY", key), ("GEMINI_MODEL", model))
                if not value
            ]
            raise AssistantNotConfigured(
                "AI_PROVIDER=gemini needs " + " and ".join(missing) + "."
            )
        return cls(
            client=_client(key),
            model=model,
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
        return self._generate(request, PARSE_ORDER_SCHEMA, ParseOrderResult)

    def classify_reply(
        self, message: MessageInput, locale: str
    ) -> Completion[ClassifyReplyResult]:
        request = prompts.classify_reply_request(message, locale)
        return self._generate(request, CLASSIFY_REPLY_SCHEMA, ClassifyReplyResult)

    def extract_car_details(
        self,
        current: CarFields,
        asked: list[str],
        message: MessageInput,
        locale: str,
    ) -> Completion[CarDetailsResult]:
        request = prompts.extract_car_request(current, asked, message, locale)
        return self._generate(request, CAR_DETAILS_SCHEMA, CarDetailsResult)

    def transcribe(
        self, audio: AudioInput, locale_hint: str
    ) -> Completion[TranscribeResult]:
        request = prompts.transcribe_request(audio, locale_hint)
        return self._generate(request, TRANSCRIBE_SCHEMA, TranscribeResult)

    # --- the request ------------------------------------------------------------------------

    def _generate(
        self,
        request: prompts.PromptRequest,
        schema: dict[str, Any],
        result_type: type[_T],
    ) -> Completion[_T]:
        contents: list[Any] = [request.context]
        if isinstance(request.message, AudioInput):
            contents.append(prompts.message_text(request.message))
            contents.append(
                genai_types.Part.from_bytes(
                    data=request.message.data, mime_type=request.message.mime_type
                )
            )
        else:
            contents.append(prompts.message_text(request.message))
        config = genai_types.GenerateContentConfig(
            system_instruction=request.system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.0,
            http_options=genai_types.HttpOptions(
                timeout=int(self.timeout_seconds * 1000)
            ),
        )
        try:
            response = self.client.models.generate_content(
                model=self.model, contents=contents, config=config
            )
        except AssistantError:
            raise
        except genai_errors.ClientError as error:
            if error.code == 429:
                raise AssistantRateLimited from error
            raise AssistantError(f"http_{error.code}") from error
        except genai_errors.APIError as error:
            raise AssistantError(f"http_{error.code}") from error
        except Exception as error:
            # The SDK's HTTP library is not ours to import (it changes between releases), so a
            # timeout is recognised by the name of its class.
            if _is_timeout(error):
                raise AssistantTimeout from error
            raise AssistantError("network") from error

        return Completion(
            value=self._validated(response, result_type),
            model=self.model,
            usage=_usage(response),
        )

    @staticmethod
    def _validated(response: Any, result_type: type[_T]) -> _T:
        text = getattr(response, "text", None)
        if not text:
            # Blocked, truncated or empty: nothing to read.
            raise AssistantInvalidOutput("empty_output")
        try:
            return result_type.model_validate(json.loads(text))
        except (ValueError, ValidationError) as error:
            # json.JSONDecodeError is a ValueError. The text is never kept or logged.
            raise AssistantInvalidOutput from error


def _is_timeout(error: BaseException) -> bool:
    return isinstance(error, TimeoutError) or any(
        "timeout" in cls.__name__.lower() for cls in type(error).__mro__
    )


def _usage(response: Any) -> Usage:
    metadata = getattr(response, "usage_metadata", None)
    return Usage(
        input_tokens=getattr(metadata, "prompt_token_count", None),
        output_tokens=getattr(metadata, "candidates_token_count", None),
    )


@cache
def _client(api_key: str) -> Any:
    return genai.Client(api_key=api_key)
