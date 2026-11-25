"""The customer-account limits. The counters themselves are shared with the staff sign-in
(``core.limits``); this module only names the customers' cache keys."""

from core.limits import clear, cooldown, digest, hit

__all__ = ["clear", "cooldown", "hit", "key_for"]


def key_for(kind: str, value: str) -> str:
    """A cache key that never holds the contact itself."""
    return f"customers:{kind}:{digest(value)}"
