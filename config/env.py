"""Readers for environment variables that fail loudly on a bad value.

A typo such as ``LOCATION_CHECK=enfroce`` or ``AI_TIMEOUT_SECONDS=fifteen`` stops Django at
start-up instead of silently falling back to a default.
"""

import os
from collections.abc import Collection

from django.core.exceptions import ImproperlyConfigured

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ImproperlyConfigured(
        f"{name} must be one of true, false, 1, 0, yes, no, on, off (got {value!r})."
    )


def env_choice(name: str, default: str, choices: Collection[str]) -> str:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    if value not in choices:
        allowed = ", ".join(sorted(choices))
        raise ImproperlyConfigured(f"{name} must be one of {allowed} (got {value!r}).")
    return value


def env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ImproperlyConfigured(
            f"{name} must be a whole number (got {raw!r})."
        ) from None
    if value < minimum:
        raise ImproperlyConfigured(f"{name} must be at least {minimum} (got {value}).")
    return value


def env_numbered(prefix: str, count: int) -> tuple[tuple[int, str], ...]:
    """The values of ``<prefix>1`` to ``<prefix><count>``, each with its number, in number order.

    An empty or missing variable is skipped, so a gap (a key removed from the middle) does not
    stop the ones after it. Values are trimmed and never printed or logged.
    """
    found = []
    for number in range(1, count + 1):
        value = os.environ.get(f"{prefix}{number}", "").strip()
        if value:
            found.append((number, value))
    return tuple(found)
