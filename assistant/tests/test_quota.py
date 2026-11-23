"""Counting what a key has been used for, and Gemini's budget from the call log."""

from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from assistant import quota
from assistant.models import AICallLog

LIMIT = quota.Limit(per_minute=2, per_day=3)
NOON = datetime(2026, 11, 23, 12, 0, 30, tzinfo=UTC).timestamp()


class TestTake:
    def test_a_key_takes_calls_up_to_its_minute_limit(self) -> None:
        taken = [quota.take("t", 1, LIMIT, now=NOON) for _ in range(3)]

        assert taken == [True, True, False]

    def test_the_next_minute_starts_again(self) -> None:
        quota.take("t", 1, LIMIT, now=NOON)
        quota.take("t", 1, LIMIT, now=NOON)

        assert quota.take("t", 1, LIMIT, now=NOON + 60) is True

    def test_a_key_stops_at_its_day_limit_whatever_the_minute(self) -> None:
        results = [quota.take("t", 1, LIMIT, now=NOON + 60 * n) for n in range(5)]

        assert results == [True, True, True, False, False]

    def test_the_next_day_starts_again(self) -> None:
        for n in range(3):
            quota.take("t", 1, LIMIT, now=NOON + 60 * n)

        assert quota.take("t", 1, LIMIT, now=NOON + 24 * 3600) is True

    def test_each_key_and_each_scope_counts_on_its_own(self) -> None:
        for _ in range(2):
            quota.take("chat", 1, LIMIT, now=NOON)

        assert quota.take("chat", 1, LIMIT, now=NOON) is False
        assert quota.take("chat", 2, LIMIT, now=NOON) is True
        assert quota.take("stt", 1, LIMIT, now=NOON) is True

    def test_a_refused_call_is_not_counted(self) -> None:
        quota.take("t", 1, LIMIT, now=NOON)
        quota.take("t", 1, LIMIT, now=NOON)
        for _ in range(5):
            quota.take("t", 1, LIMIT, now=NOON)

        # Still the day's third call is available a minute later: the refusals cost nothing.
        assert quota.take("t", 1, LIMIT, now=NOON + 60) is True

    def test_has_room_counts_nothing(self) -> None:
        for _ in range(5):
            assert quota.has_room("t", 1, LIMIT, now=NOON) is True

        quota.take("t", 1, LIMIT, now=NOON)
        quota.take("t", 1, LIMIT, now=NOON)

        assert quota.has_room("t", 1, LIMIT, now=NOON) is False


class TestRest:
    def test_a_resting_key_takes_nothing(self) -> None:
        quota.rest("t", 1, 60, now=NOON)

        assert quota.has_room("t", 1, LIMIT, now=NOON) is False
        assert quota.take("t", 1, LIMIT, now=NOON) is False
        assert quota.take("t", 2, LIMIT, now=NOON) is True

    def test_a_rest_of_no_seconds_still_lasts_a_moment(self) -> None:
        quota.rest("t", 1, 0, now=NOON)

        assert quota.has_room("t", 1, LIMIT, now=NOON) is False


@pytest.mark.django_db
class TestGeminiBudget:
    def _call(
        self, outcome: str = "ok", provider: str = "gemini", **extra: object
    ) -> None:
        AICallLog.objects.create(
            provider=provider,
            purpose="parse_order",
            input_kind="text",
            outcome=outcome,
            **extra,
        )

    def test_it_counts_todays_gemini_calls_only(self) -> None:
        self._call()
        self._call()
        self._call(provider="groq")
        old = AICallLog.objects.create(
            provider="gemini", purpose="parse_order", input_kind="text", outcome="ok"
        )
        AICallLog.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=2)
        )

        assert quota.gemini_calls_today() == 2

    def test_calls_the_backend_or_google_refused_do_not_count(self) -> None:
        self._call()
        self._call("budget_exceeded")
        self._call("rate_limited")
        self._call("timeout")  # Google may have counted it

        assert quota.gemini_calls_today() == 2

    def test_the_budget_is_the_setting(self, settings: object) -> None:
        settings.GEMINI_DAILY_REQUEST_LIMIT = 2  # type: ignore[attr-defined]
        self._call()
        assert quota.gemini_budget_left() is True

        self._call()
        assert quota.gemini_budget_left() is False

    def test_the_day_starts_at_midnight_pacific(self) -> None:
        # 2026-11-23 06:00 UTC is 22:00 on the 22nd in Pacific time (UTC-8 in November).
        start = quota.pacific_day_start(datetime(2026, 11, 23, 6, 0, tzinfo=UTC))

        assert start.astimezone(UTC) == datetime(2026, 11, 22, 8, 0, tzinfo=UTC)
