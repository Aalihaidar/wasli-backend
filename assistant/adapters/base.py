from abc import ABC, abstractmethod
from typing import Any

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
)


class AssistantAdapter(ABC):
    """What every provider implements (``AI_PROVIDER`` picks one).

    An adapter turns the customer's text or voice into structured data and nothing else. Each
    method returns a validated ``Completion`` or raises an ``AssistantError``; the layer around
    it (``assistant.services``) checks the caps first and logs every call.
    """

    #: Short name written to ``AICallLog.provider``.
    name: str

    @abstractmethod
    def parse_order(
        self,
        menu: PromptMenu,
        lines: list[CurrentLine],
        pending_question: dict[str, Any] | None,
        message: MessageInput,
        locale: str,
    ) -> Completion[ParseOrderResult]:
        """What the customer wants to change in their order."""

    @abstractmethod
    def classify_reply(
        self, message: MessageInput, locale: str
    ) -> Completion[ClassifyReplyResult]:
        """What a reply to the final summary means: confirm, edit, cancel or unclear."""

    @abstractmethod
    def extract_car_details(
        self,
        current: CarFields,
        asked: list[str],
        message: MessageInput,
        locale: str,
    ) -> Completion[CarDetailsResult]:
        """The parking note, plate, model and colour out of one answer."""

    @abstractmethod
    def transcribe(
        self, audio: AudioInput, locale_hint: str
    ) -> Completion[TranscribeResult]:
        """The words of a voice note."""
