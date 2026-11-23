"""What a turn takes and gives: the customer's button and the bot's message before it is stored."""

from dataclasses import dataclass, field
from typing import Any

from .models import MessageKind


@dataclass(frozen=True)
class Action:
    """A button the customer tapped, or the app's own request (the item picker)."""

    name: str
    field_name: str = ""
    value: str = ""
    locale: str = ""
    lines: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Reply:
    """One bot message, before it is stored."""

    text: str
    kind: str = MessageKind.TEXT
    payload: dict[str, Any] = field(default_factory=dict)
    image: str = ""


def quick_replies(*buttons: dict[str, str]) -> dict[str, Any]:
    return {"quick_replies": list(buttons)}
