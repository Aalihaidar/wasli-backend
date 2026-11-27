from typing import Any, cast

from django.conf import settings


def test_tests_never_use_a_real_assistant_provider() -> None:
    assert settings.AI_PROVIDER == "fake"


def test_wasli_settings_have_valid_values() -> None:
    assert settings.ENVIRONMENT in {"local", "staging", "production"}
    assert settings.LOCATION_CHECK in {"off", "warn", "enforce"}
    assert isinstance(settings.REQUIRE_SCREEN_ONLINE, bool)
    assert isinstance(settings.REQUIRE_VERIFIED_PHONE, bool)
    assert settings.AI_TIMEOUT_SECONDS >= 1
    assert settings.GEMINI_DAILY_REQUEST_LIMIT >= 0


def test_log_lines_name_the_environment() -> None:
    logging_config = cast("dict[str, Any]", settings.LOGGING)
    log_format = logging_config["formatters"]["plain"]["format"]

    assert f"[{settings.ENVIRONMENT}]" in log_format


def test_log_lines_carry_the_request_id() -> None:
    logging_config = cast("dict[str, Any]", settings.LOGGING)

    assert "[{request_id}]" in logging_config["formatters"]["plain"]["format"]
    assert logging_config["handlers"]["console"]["filters"] == ["request_id"]


def test_the_admin_keeps_djangos_default_upload_handlers() -> None:
    """Only the voice endpoint reads an upload in memory (chat/uploads.py); the admin's image
    uploads keep Django's handlers, which write a large file to a temporary file instead of
    dropping it."""
    assert settings.FILE_UPLOAD_HANDLERS == [
        "django.core.files.uploadhandler.MemoryFileUploadHandler",
        "django.core.files.uploadhandler.TemporaryFileUploadHandler",
    ]
