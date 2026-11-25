"""The cache counters shared by the customer and the staff sign-in."""

import pytest
from django.core.cache import cache
from rest_framework.exceptions import Throttled

from core import limits


def test_the_limit_plus_one_th_use_is_refused() -> None:
    key = "test:limits:hit"

    for _ in range(3):
        limits.hit(key, limit=3, window_seconds=60)

    with pytest.raises(Throttled):
        limits.hit(key, limit=3, window_seconds=60)


def test_a_refusal_says_how_long_to_wait() -> None:
    key = "test:limits:wait"
    limits.hit(key, limit=1, window_seconds=90)

    with pytest.raises(Throttled) as refused:
        limits.hit(key, limit=1, window_seconds=90)

    assert refused.value.wait == 90


def test_clear_starts_the_count_again() -> None:
    key = "test:limits:clear"
    limits.hit(key, limit=1, window_seconds=60)

    limits.clear(key)

    limits.hit(key, limit=1, window_seconds=60)


def test_a_counter_that_expired_between_the_two_calls_starts_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = "test:limits:expired"
    cache.set(key, 5, timeout=60)

    def gone(*args: object, **kwargs: object) -> int:
        cache.delete(key)
        raise ValueError

    monkeypatch.setattr(cache, "incr", gone)

    limits.hit(key, limit=1, window_seconds=60)

    assert cache.get(key) == 1


def test_a_second_use_inside_the_cooldown_is_refused() -> None:
    key = "test:limits:cooldown"
    limits.cooldown(key, seconds=30)

    with pytest.raises(Throttled) as refused:
        limits.cooldown(key, seconds=30)

    assert 1 <= (refused.value.wait or 0) <= 31


def test_the_digest_is_stable_and_never_holds_the_value() -> None:
    first = limits.digest("cafe-cashier")

    assert first == limits.digest("cafe-cashier")
    assert first != limits.digest("cafe-admin")
    assert "cashier" not in first
    assert len(first) == 32
