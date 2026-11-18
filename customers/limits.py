"""Small counters in the cache for the limits that must not depend on whether an account exists.

They are kept in the process cache, so each Gunicorn worker counts for itself (the same as the
DRF throttles of this project). They are a brake against guessing and against spending SMS, not
an accounting system.
"""

import hashlib
import time

from django.core.cache import cache
from rest_framework.exceptions import Throttled


def key_for(kind: str, value: str) -> str:
    """A cache key that never holds the contact itself."""
    return f"customers:{kind}:{hashlib.sha256(value.encode()).hexdigest()[:32]}"


def hit(key: str, *, limit: int, window_seconds: int) -> None:
    """Count one use; refuse the ``limit`` + 1 th use inside the window."""
    if cache.add(key, 1, timeout=window_seconds):
        return
    try:
        count = cache.incr(key)
    except ValueError:  # the key expired between the two calls
        cache.set(key, 1, timeout=window_seconds)
        return
    if count > limit:
        raise Throttled(wait=window_seconds)


def clear(key: str) -> None:
    cache.delete(key)


def cooldown(key: str, *, seconds: int) -> None:
    """Refuse a second use before ``seconds`` have passed since the first."""
    now = time.time()
    last = cache.get(key)
    if last is not None and now - last < seconds:
        raise Throttled(wait=int(seconds - (now - last)) + 1)
    cache.set(key, now, timeout=seconds)
