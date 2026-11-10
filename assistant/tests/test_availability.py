import pytest

from assistant.availability import ai_enabled


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
