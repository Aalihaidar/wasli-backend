"""Counting what a provider key has been used for, so the backend stays under its limits.

Groq limits what one key may do with one model per minute and per day, and Gemini's free tier
limits a project per day. The backend counts its own calls and stops before the provider does;
a provider that says "too many requests" anyway puts that key to rest for the time it names.

Two kinds of counter, each where it is cheapest and most exact:

- **Groq keys** count in the cache (a fixed minute and a fixed day per key and model), because a
  call is checked before every request. The cache is per worker process and starts empty after a
  restart, so the count is a good estimate and the provider's own refusal is the safety net.
- **Gemini** counts the day's rows of the call log (``AICallLog``), which are exact across
  workers and restarts and need no extra storage.
"""

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

PACIFIC = ZoneInfo("America/Los_Angeles")


@dataclass(frozen=True)
class Limit:
    """What one key may do with one model."""

    per_minute: int
    per_day: int


def _day(now: float, tz: ZoneInfo | None = None) -> str:
    return datetime.fromtimestamp(now, tz or UTC).strftime("%Y%m%d")


def _keys(scope: str, slot: int, now: float) -> tuple[str, str, str]:
    base = f"quota:{scope}:{slot}"
    return f"{base}:m:{int(now // 60)}", f"{base}:d:{_day(now)}", f"{base}:rest"


def has_room(scope: str, slot: int, limit: Limit, *, now: float | None = None) -> bool:
    """Whether the key could take one more call right now. Counts nothing."""
    moment = time.time() if now is None else now
    minute, day, rest = _keys(scope, slot, moment)
    return (
        not cache.get(rest, False)
        and int(cache.get(minute, 0)) < limit.per_minute
        and int(cache.get(day, 0)) < limit.per_day
    )


def take(scope: str, slot: int, limit: Limit, *, now: float | None = None) -> bool:
    """Count one call for the key and return True, or return False (counting nothing) when the
    key is resting or has used its minute or its day."""
    moment = time.time() if now is None else now
    if not has_room(scope, slot, limit, now=moment):
        return False
    minute, day, _ = _keys(scope, slot, moment)
    for key, ttl in ((minute, 120), (day, 2 * 86400)):
        cache.add(key, 0, ttl)
        cache.incr(key)
    return True


def rest(scope: str, slot: int, seconds: int, *, now: float | None = None) -> None:
    """Leave the key alone for ``seconds`` (the provider asked, or the key was refused)."""
    moment = time.time() if now is None else now
    cache.set(_keys(scope, slot, moment)[2], True, max(1, seconds))


# --- Gemini's daily budget, counted from the call log ---------------------------------------


def pacific_day_start(now: datetime | None = None) -> datetime:
    """Midnight Pacific that began the current day, as Google resets its daily quota."""
    local = (now or timezone.now()).astimezone(PACIFIC)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def gemini_calls_today() -> int:
    """Gemini calls since midnight Pacific. A call the backend refused itself, and one Google
    answered with "too many requests", did not use the quota."""
    from assistant.models import AICallLog, Outcome

    return (
        AICallLog.objects.filter(provider="gemini", created_at__gte=pacific_day_start())
        .exclude(outcome__in=[Outcome.BUDGET_EXCEEDED, Outcome.RATE_LIMITED])
        .count()
    )


def gemini_budget_left() -> bool:
    return gemini_calls_today() < settings.GEMINI_DAILY_REQUEST_LIMIT
