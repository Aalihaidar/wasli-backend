from typing import Any, cast

from django.conf import settings


def test_tests_never_use_a_real_assistant_provider() -> None:
    assert settings.AI_PROVIDER == "fake"


def test_wasli_settings_have_valid_values() -> None:
    assert settings.ENVIRONMENT in {"local", "staging", "production"}
    assert settings.LOCATION_CHECK in {"off", "warn", "enforce"}
    assert isinstance(settings.REQUIRE_SCREEN_ONLINE, bool)
    assert settings.AI_TIMEOUT_SECONDS >= 1
    assert settings.AI_DAILY_REQUEST_LIMIT >= 0


def test_log_lines_name_the_environment() -> None:
    logging_config = cast("dict[str, Any]", settings.LOGGING)
    log_format = logging_config["formatters"]["plain"]["format"]

    assert f"[{settings.ENVIRONMENT}]" in log_format
