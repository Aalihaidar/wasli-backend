"""Whether the assistant layer can be used right now.

``ai_enabled`` is the configuration (for ``GET /config``): the fake provider is always usable,
Gemini needs its key and model, and Groq needs at least one key and both model codes.
``ai_available`` is what a conversation reports: the same, and not within five minutes after the
provider failed (an error, a timeout or a rate limit), and not when the provider's budget is used
up (Gemini's day, or every Groq key at its limit), so the chat stops waiting on a provider that
cannot answer and offers the item picker instead.

The failure is remembered in the cache, which is per worker process: one worker may learn of an
outage a little before another, which only means one more customer waits for one timeout.
"""

from django.conf import settings
from django.core.cache import cache

from . import quota
from .keys import CHAT, KeyPool

# How long after a provider failure the assistant is reported as unavailable.
FAILURE_WINDOW_SECONDS = 5 * 60
_FAILURE_KEY = "assistant:failed"


def ai_enabled() -> bool:
    """The fake provider is always usable; the others need their keys and model codes."""
    if settings.AI_PROVIDER == "fake":
        return True
    if settings.AI_PROVIDER == "groq":
        return bool(
            settings.GROQ_API_KEYS
            and settings.GROQ_CHAT_MODEL
            and settings.GROQ_STT_MODEL
        )
    return bool(settings.GEMINI_API_KEY and settings.GEMINI_MODEL)


def _budget_left() -> bool:
    if settings.AI_PROVIDER == "gemini":
        return quota.gemini_budget_left()
    if settings.AI_PROVIDER == "groq":
        return KeyPool.from_settings().has_room(CHAT)
    return True


def record_failure() -> None:
    """The provider just failed: report the assistant as unavailable for a few minutes."""
    cache.set(_FAILURE_KEY, True, FAILURE_WINDOW_SECONDS)


def ai_available() -> bool:
    return ai_enabled() and not cache.get(_FAILURE_KEY, False) and _budget_left()
