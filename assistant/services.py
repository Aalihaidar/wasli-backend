"""The assistant layer the rest of the project calls.

``Assistant`` checks the caps, calls the adapter chosen by ``AI_PROVIDER`` and writes one
``AICallLog`` row per call: provider, model, purpose, input kind, latency, tokens and outcome.
Never the content: not what the customer wrote or said, not what the provider answered.

A failed call raises an ``AssistantError``; the conversation then uses its no-assistant path
(the item picker, one car question at a time). Nothing is retried inside a customer's request.
"""

import time
from collections.abc import Callable
from typing import Any, TypeVar

from django.conf import settings
from pydantic import BaseModel

from . import limits, quota
from .adapters.base import AssistantAdapter
from .adapters.fake import FakeAdapter
from .errors import AssistantBudgetExceeded, AssistantError, AssistantInputError
from .models import AICallLog, InputKind, Outcome, Purpose
from .types import (
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
)

_R = TypeVar("_R", bound=BaseModel)


def get_adapter(provider: str | None = None) -> AssistantAdapter:
    """The adapter named by ``AI_PROVIDER`` (``groq``, ``gemini`` or ``fake``), or by
    ``provider`` when the developer spike compares another one."""
    chosen = provider or settings.AI_PROVIDER
    if chosen == "groq":
        from .adapters.groq import GroqAdapter

        return GroqAdapter.from_settings()
    if chosen == "gemini":
        from .adapters.gemini import GeminiAdapter

        return GeminiAdapter.from_settings()
    return FakeAdapter.recorded()


def check_budget(provider: str) -> None:
    """Refuse a call when the provider's day is used up. Only Gemini has a daily budget counted
    here; Groq keys count their own minute and day while they are chosen (``assistant.keys``)."""
    if provider == "gemini" and not quota.gemini_budget_left():
        raise AssistantBudgetExceeded


def check_message(message: MessageInput) -> None:
    """Refuse an input over a cap before it is sent anywhere."""
    if isinstance(message, AudioInput):
        if message.mime_type not in limits.ACCEPTED_AUDIO_TYPES:
            raise AssistantInputError(f"Unsupported audio type {message.mime_type!r}.")
        if not message.data:
            raise AssistantInputError("The audio is empty.")
        if len(message.data) > limits.MAX_AUDIO_BYTES:
            raise AssistantInputError("The audio is larger than the cap.")
    elif len(message) > limits.MAX_TEXT_CHARS:
        raise AssistantInputError("The text is longer than the cap.")


class Assistant:
    def __init__(self, adapter: AssistantAdapter | None = None) -> None:
        self._adapter = adapter

    @property
    def adapter(self) -> AssistantAdapter:
        if self._adapter is None:
            self._adapter = get_adapter()
        return self._adapter

    def parse_order(
        self,
        menu: PromptMenu,
        lines: list[CurrentLine],
        pending_question: dict[str, Any] | None,
        message: MessageInput,
        locale: str,
        *,
        restaurant: Any = None,
        conversation: Any = None,
    ) -> ParseOrderResult:
        return self._call(
            Purpose.PARSE_ORDER,
            message,
            lambda: self.adapter.parse_order(
                menu, lines, pending_question, message, locale
            ),
            restaurant,
            conversation,
        )

    def classify_reply(
        self,
        message: MessageInput,
        locale: str,
        *,
        restaurant: Any = None,
        conversation: Any = None,
    ) -> ClassifyReplyResult:
        return self._call(
            Purpose.CLASSIFY_REPLY,
            message,
            lambda: self.adapter.classify_reply(message, locale),
            restaurant,
            conversation,
        )

    def extract_car_details(
        self,
        current: CarFields,
        asked: list[str],
        message: MessageInput,
        locale: str,
        *,
        restaurant: Any = None,
        conversation: Any = None,
    ) -> CarDetailsResult:
        return self._call(
            Purpose.EXTRACT_CAR,
            message,
            lambda: self.adapter.extract_car_details(current, asked, message, locale),
            restaurant,
            conversation,
        )

    def transcribe(
        self,
        audio: AudioInput,
        locale_hint: str,
        *,
        restaurant: Any = None,
        conversation: Any = None,
    ) -> TranscribeResult:
        return self._call(
            Purpose.TRANSCRIBE,
            audio,
            lambda: self.adapter.transcribe(audio, locale_hint),
            restaurant,
            conversation,
        )

    def _call(
        self,
        purpose: str,
        message: MessageInput,
        run: Callable[[], Completion[_R]],
        restaurant: Any,
        conversation: Any,
    ) -> _R:
        check_message(message)
        started = time.monotonic()
        outcome: str = Outcome.OK
        error_code = ""
        completion: Completion[_R] | None = None
        try:
            check_budget(self.adapter.name)
            completion = run()
        except AssistantError as error:
            outcome, error_code = error.outcome, error.code
            raise
        except Exception:
            # Whatever else went wrong is a failure of the provider, not of the customer.
            outcome, error_code = Outcome.ERROR, "unexpected"
            raise AssistantError("unexpected") from None
        finally:
            AICallLog.objects.create(
                restaurant=restaurant,
                conversation=conversation,
                provider=self.adapter.name,
                model=completion.model if completion else _model_name(self.adapter),
                purpose=purpose,
                input_kind=InputKind.AUDIO
                if isinstance(message, AudioInput)
                else InputKind.TEXT,
                latency_ms=int((time.monotonic() - started) * 1000),
                input_tokens=completion.usage.input_tokens if completion else None,
                output_tokens=completion.usage.output_tokens if completion else None,
                outcome=outcome,
                error_code=error_code,
            )
        return completion.value


def _model_name(adapter: AssistantAdapter) -> str:
    return str(getattr(adapter, "model", "") or "")
