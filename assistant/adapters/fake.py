"""The adapter every test uses: no network, no key, no randomness.

It replays recorded outputs. ``FakeAdapter.recorded()`` knows the examples of the spec (the car
answers in English and Arabic, a confirm and an edit); a test that needs something else scripts
it with ``FakeAdapter(script=...)`` and can make a call fail to test the fallbacks.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from assistant.errors import AssistantError
from assistant.types import (
    AudioInput,
    CarDetailsResult,
    CarFields,
    ClassifyReplyResult,
    Completion,
    CurrentLine,
    Language,
    MessageInput,
    OrderIntent,
    ParseOrderResult,
    PromptMenu,
    ReplyField,
    ReplyIntent,
    TranscribeResult,
)

from .base import AssistantAdapter


@dataclass(frozen=True)
class Call:
    """One call the fake received, so a test can check what the layer asked."""

    purpose: str
    message: MessageInput
    locale: str
    args: dict[str, Any]


def _key(message: MessageInput) -> str:
    if isinstance(message, AudioInput):
        return message.data.decode("utf-8", errors="ignore").strip().lower()
    return message.strip().lower()


_UNCLEAR_ORDER = ParseOrderResult(language=Language.EN, intent=OrderIntent.UNCLEAR)

_CAR_EN = CarDetailsResult(
    transcript=None,
    language=Language.EN,
    parking_note="Parking B2 near the lift",
    plate="A 12345",
    model="Toyota Camry",
    colour="White",
)
_CAR_AR = CarDetailsResult(
    transcript=None,
    language=Language.AR,
    parking_note="باركنغ B2 قرب المصعد",
    plate="A 12345",
    model="تويوتا كامري",
    colour="بيضاء",
)
_CAR_PARTIAL = CarDetailsResult(
    transcript=None,
    language=Language.EN,
    parking_note="At the entrance",
    colour="Black",
)

RECORDED_CARS: dict[str, CarDetailsResult] = {
    "parking b2 near the lift, plate a 12345, white toyota camry": _CAR_EN,
    "i'm at the entrance, the car is black": _CAR_PARTIAL,
    "أنا في باركنغ b2 قرب المصعد، رقم السيارة a 12345، تويوتا كامري بيضاء": _CAR_AR,
}
RECORDED_REPLIES: dict[str, ClassifyReplyResult] = {
    "yes, send it": ClassifyReplyResult(
        language=Language.EN, intent=ReplyIntent.CONFIRM
    ),
    "yes": ClassifyReplyResult(language=Language.EN, intent=ReplyIntent.CONFIRM),
    "نعم": ClassifyReplyResult(language=Language.AR, intent=ReplyIntent.CONFIRM),
    "change the note": ClassifyReplyResult(
        language=Language.EN, intent=ReplyIntent.EDIT, field=ReplyField.NOTE
    ),
    "forget it": ClassifyReplyResult(language=Language.EN, intent=ReplyIntent.CANCEL),
}
RECORDED_TRANSCRIPTS: dict[str, TranscribeResult] = {
    "no straw please": TranscribeResult(
        transcript="No straw please", language=Language.EN
    ),
    "بدون قشة": TranscribeResult(transcript="بدون قشة", language=Language.AR),
}


class FakeAdapter(AssistantAdapter):
    """Replays scripted answers keyed by what the customer wrote (lower case, trimmed).

    ``script`` maps ``(purpose, text)`` to a result, or to a callable that builds one from the
    call's arguments. ``fail_with`` makes every call raise that error. A message nobody scripted
    gets the neutral answer (``unclear``, all fields empty), like a provider that understood
    nothing.
    """

    name = "fake"

    def __init__(
        self,
        script: dict[tuple[str, str], Any] | None = None,
        *,
        fail_with: AssistantError | None = None,
    ) -> None:
        self.script = {
            (purpose, text.strip().lower()): value
            for (purpose, text), value in (script or {}).items()
        }
        self.fail_with = fail_with
        self.calls: list[Call] = []

    @classmethod
    def recorded(cls) -> FakeAdapter:
        script: dict[tuple[str, str], Any] = {}
        script.update({("extract_car_details", k): v for k, v in RECORDED_CARS.items()})
        script.update({("classify_reply", k): v for k, v in RECORDED_REPLIES.items()})
        script.update({("transcribe", k): v for k, v in RECORDED_TRANSCRIPTS.items()})
        return cls(script)

    def _answer(
        self,
        purpose: str,
        message: MessageInput,
        locale: str,
        args: dict[str, Any],
        neutral: Any,
    ) -> Any:
        self.calls.append(Call(purpose, message, locale, args))
        if self.fail_with is not None:
            raise self.fail_with
        found = self.script.get((purpose, _key(message)), neutral)
        return found(**args) if isinstance(found, Callable) else found  # type: ignore[arg-type]

    def parse_order(
        self,
        menu: PromptMenu,
        lines: list[CurrentLine],
        pending_question: dict[str, Any] | None,
        message: MessageInput,
        locale: str,
    ) -> Completion[ParseOrderResult]:
        value = self._answer(
            "parse_order",
            message,
            locale,
            {"menu": menu, "lines": lines, "pending_question": pending_question},
            _UNCLEAR_ORDER,
        )
        return Completion(value, model="fake")

    def classify_reply(
        self, message: MessageInput, locale: str
    ) -> Completion[ClassifyReplyResult]:
        value = self._answer(
            "classify_reply",
            message,
            locale,
            {},
            ClassifyReplyResult(intent=ReplyIntent.UNCLEAR),
        )
        return Completion(value, model="fake")

    def extract_car_details(
        self,
        current: CarFields,
        asked: list[str],
        message: MessageInput,
        locale: str,
    ) -> Completion[CarDetailsResult]:
        value = self._answer(
            "extract_car_details",
            message,
            locale,
            {"current": current, "asked": asked},
            CarDetailsResult(),
        )
        return Completion(value, model="fake")

    def transcribe(
        self, audio: AudioInput, locale_hint: str
    ) -> Completion[TranscribeResult]:
        value = self._answer(
            "transcribe", audio, locale_hint, {}, TranscribeResult(transcript=None)
        )
        return Completion(value, model="fake")
