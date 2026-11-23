import pytest

from assistant.availability import (
    FAILURE_WINDOW_SECONDS,
    ai_available,
    ai_enabled,
    record_failure,
)


class TestAiEnabled:
    def test_the_fake_provider_is_always_usable(self, settings: object) -> None:
        settings.AI_PROVIDER = "fake"  # type: ignore[attr-defined]
        settings.GEMINI_API_KEY = ""  # type: ignore[attr-defined]

        assert ai_enabled() is True

    @pytest.mark.parametrize(
        ("key", "model", "expected"),
        [
            ("invented-key", "invented-model", True),
            ("", "invented-model", False),
            ("invented-key", "", False),
            ("", "", False),
        ],
    )
    def test_gemini_needs_its_key_and_its_model(
        self, settings: object, key: str, model: str, expected: bool
    ) -> None:
        settings.AI_PROVIDER = "gemini"  # type: ignore[attr-defined]
        settings.GEMINI_API_KEY = key  # type: ignore[attr-defined]
        settings.GEMINI_MODEL = model  # type: ignore[attr-defined]

        assert ai_enabled() is expected


class TestAiAvailable:
    def test_it_follows_the_configuration_until_the_provider_fails(
        self, settings: object
    ) -> None:
        settings.AI_PROVIDER = "fake"  # type: ignore[attr-defined]

        assert ai_available() is True

        record_failure()

        assert ai_available() is False
        assert ai_enabled() is True  # the configuration itself did not change

    def test_the_window_is_five_minutes(self, settings: object) -> None:
        from django.core.cache import cache

        settings.AI_PROVIDER = "fake"  # type: ignore[attr-defined]
        record_failure()

        assert FAILURE_WINDOW_SECONDS == 5 * 60
        cache.delete("assistant:failed")  # what the cache does when the window ends
        assert ai_available() is True

    def test_a_missing_key_is_unavailable_without_any_failure(
        self, settings: object
    ) -> None:
        settings.AI_PROVIDER = "gemini"  # type: ignore[attr-defined]
        settings.GEMINI_API_KEY = ""  # type: ignore[attr-defined]

        assert ai_available() is False


class TestTheProvidersBudget:
    def test_groq_needs_a_key_and_both_models(self, settings: object) -> None:
        settings.AI_PROVIDER = "groq"  # type: ignore[attr-defined]
        settings.GROQ_API_KEYS = ((1, "k"),)  # type: ignore[attr-defined]
        settings.GROQ_CHAT_MODEL = "c"  # type: ignore[attr-defined]
        settings.GROQ_STT_MODEL = "s"  # type: ignore[attr-defined]
        assert ai_enabled() is True

        for name in ("GROQ_CHAT_MODEL", "GROQ_STT_MODEL"):
            old = getattr(settings, name)
            setattr(settings, name, "")
            assert ai_enabled() is False
            setattr(settings, name, old)

        settings.GROQ_API_KEYS = ()  # type: ignore[attr-defined]
        assert ai_enabled() is False

    def test_groq_is_unavailable_when_every_key_is_at_its_limit(
        self, settings: object
    ) -> None:
        from assistant import keys

        settings.AI_PROVIDER = "groq"  # type: ignore[attr-defined]
        settings.GROQ_API_KEYS = ((1, "k"), (2, "j"))  # type: ignore[attr-defined]
        settings.GROQ_CHAT_MODEL = "c"  # type: ignore[attr-defined]
        settings.GROQ_STT_MODEL = "s"  # type: ignore[attr-defined]
        settings.GROQ_CHAT_RPM = 1  # type: ignore[attr-defined]
        pool = keys.KeyPool.from_settings()
        assert ai_available() is True

        pool.take(keys.CHAT)
        assert ai_available() is True  # the second key still has room
        pool.take(keys.CHAT)
        assert ai_available() is False

    @pytest.mark.django_db
    def test_gemini_is_unavailable_when_its_day_is_used_up(
        self, settings: object
    ) -> None:
        from assistant.models import AICallLog

        settings.AI_PROVIDER = "gemini"  # type: ignore[attr-defined]
        settings.GEMINI_API_KEY = "k"  # type: ignore[attr-defined]
        settings.GEMINI_MODEL = "m"  # type: ignore[attr-defined]
        settings.GEMINI_DAILY_REQUEST_LIMIT = 1  # type: ignore[attr-defined]
        assert ai_available() is True

        AICallLog.objects.create(
            provider="gemini", purpose="parse_order", input_kind="text", outcome="ok"
        )

        assert ai_available() is False
        assert ai_enabled() is True
