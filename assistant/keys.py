"""The Groq keys, used in order.

The first key is used until it cannot take another call (it reached its limit for the minute or
the day, or Groq asked it to wait); then the second, and so on. The scan always starts at the
first key, so when a limit resets the first key is used again, and after the last key the backend
is back at the first. A key Groq refuses (a revoked or wrong key) is left alone for an hour.

Which key was used is never written to the call log or to any other log, and a key never appears
in an error.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from django.conf import settings

from . import quota

CHAT = "chat"
STT = "stt"

# How long a key that Groq refused (401 or 403) is left alone.
REFUSED_REST_SECONDS = 3600


@dataclass(frozen=True)
class Slot:
    number: int
    key: str


def limit_for(kind: str) -> quota.Limit:
    if kind == STT:
        return quota.Limit(settings.GROQ_STT_RPM, settings.GROQ_STT_RPD)
    return quota.Limit(settings.GROQ_CHAT_RPM, settings.GROQ_CHAT_RPD)


class KeyPool:
    """Hands out the first key that has room for one more call of a kind (``chat`` or ``stt``)."""

    def __init__(self, keys: Sequence[tuple[int, str]]) -> None:
        self.slots = [Slot(number, key) for number, key in keys]

    @classmethod
    def from_settings(cls) -> KeyPool:
        return cls(settings.GROQ_API_KEYS)

    def take(self, kind: str, skip: frozenset[int] = frozenset()) -> Slot | None:
        """The first key with room, with the call counted against it; ``skip`` leaves out
        keys already tried for this request."""
        limit = limit_for(kind)
        for slot in self.slots:
            if slot.number not in skip and quota.take(
                f"groq:{kind}", slot.number, limit
            ):
                return slot
        return None

    def has_room(self, kind: str) -> bool:
        limit = limit_for(kind)
        return any(
            quota.has_room(f"groq:{kind}", slot.number, limit) for slot in self.slots
        )

    def rest(self, kind: str, slot: Slot, seconds: int) -> None:
        quota.rest(f"groq:{kind}", slot.number, seconds)
