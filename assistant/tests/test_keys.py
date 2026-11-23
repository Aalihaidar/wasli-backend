"""The Groq keys are used in order, and the first is used again once it has room."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from assistant import keys, quota


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    now = SimpleNamespace(
        value=datetime(2026, 11, 23, 12, 0, 5, tzinfo=UTC).timestamp()
    )
    monkeypatch.setattr(quota, "time", SimpleNamespace(time=lambda: now.value))
    return now


@pytest.fixture(autouse=True)
def small_limits(settings: object) -> None:
    settings.GROQ_CHAT_RPM = 2  # type: ignore[attr-defined]
    settings.GROQ_CHAT_RPD = 100  # type: ignore[attr-defined]
    settings.GROQ_STT_RPM = 1  # type: ignore[attr-defined]
    settings.GROQ_STT_RPD = 100  # type: ignore[attr-defined]


def pool(*numbers: int) -> keys.KeyPool:
    return keys.KeyPool([(n, f"key-{n}") for n in numbers])


def used(p: keys.KeyPool, kind: str, times: int) -> list[int | None]:
    return [(slot.number if (slot := p.take(kind)) else None) for _ in range(times)]


def test_the_first_key_is_used_until_it_is_full_then_the_second(
    clock: SimpleNamespace,
) -> None:
    assert used(pool(1, 2, 3), keys.CHAT, 5) == [1, 1, 2, 2, 3]


def test_when_every_key_is_full_nothing_is_handed_out(clock: SimpleNamespace) -> None:
    p = pool(1, 2)

    assert used(p, keys.CHAT, 5) == [1, 1, 2, 2, None]
    assert p.has_room(keys.CHAT) is False


def test_after_the_last_key_it_goes_back_to_the_first(clock: SimpleNamespace) -> None:
    p = pool(1, 2)
    used(p, keys.CHAT, 4)

    clock.value += 60  # the minute passes: every key has room again

    assert used(p, keys.CHAT, 3) == [1, 1, 2]


def test_the_first_key_comes_back_while_the_others_are_still_full(
    clock: SimpleNamespace,
) -> None:
    p = pool(1, 2)
    used(p, keys.CHAT, 4)
    p.rest(keys.CHAT, keys.Slot(2, "key-2"), 3600)

    clock.value += 60

    assert used(p, keys.CHAT, 3) == [1, 1, None]


def test_a_key_that_groq_asked_to_wait_is_skipped(clock: SimpleNamespace) -> None:
    p = pool(1, 2)
    p.rest(keys.CHAT, keys.Slot(1, "key-1"), 120)

    assert used(p, keys.CHAT, 2) == [2, 2]


def test_a_request_can_skip_the_keys_it_already_tried(clock: SimpleNamespace) -> None:
    p = pool(1, 2)

    slot = p.take(keys.CHAT, frozenset({1}))

    assert slot is not None and slot.number == 2


def test_voice_and_text_count_separately(clock: SimpleNamespace) -> None:
    p = pool(1)

    assert used(p, keys.STT, 2) == [1, None]  # one transcription a minute here
    assert used(p, keys.CHAT, 2) == [1, 1]


def test_slot_numbers_survive_a_gap(clock: SimpleNamespace) -> None:
    assert used(pool(1, 4), keys.CHAT, 3) == [1, 1, 4]


def test_the_pool_is_built_from_the_settings(settings: object) -> None:
    settings.GROQ_API_KEYS = ((2, "b"), (5, "e"))  # type: ignore[attr-defined]

    assert [(s.number, s.key) for s in keys.KeyPool.from_settings().slots] == [
        (2, "b"),
        (5, "e"),
    ]


def test_the_limits_come_from_the_settings(settings: object) -> None:
    assert keys.limit_for(keys.CHAT) == quota.Limit(2, 100)
    assert keys.limit_for(keys.STT) == quota.Limit(1, 100)
