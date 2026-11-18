from typing import Any

import pytest
from rest_framework.test import APIClient

URL = "/api/v1/config"


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def test_the_config_is_public_and_complete(api: APIClient, settings: Any) -> None:
    settings.LOCATION_CHECK = "warn"
    settings.REQUIRE_SCREEN_ONLINE = False
    settings.AI_PROVIDER = "fake"

    response = api.get(URL)

    assert response.status_code == 200
    assert response.json() == {
        "location_check": "warn",
        "require_screen_online": False,
        "ai_enabled": True,
        "languages": ["en", "ar"],
        "poll_interval_seconds": 3,
    }


@pytest.mark.parametrize("value", ["off", "warn", "enforce"])
def test_it_reports_the_location_rule(
    api: APIClient, settings: Any, value: str
) -> None:
    settings.LOCATION_CHECK = value

    assert api.get(URL).json()["location_check"] == value


def test_it_reports_whether_a_restaurant_must_be_online(
    api: APIClient, settings: Any
) -> None:
    settings.REQUIRE_SCREEN_ONLINE = True

    assert api.get(URL).json()["require_screen_online"] is True


def test_it_reports_that_the_assistant_is_missing(
    api: APIClient, settings: Any
) -> None:
    settings.AI_PROVIDER = "gemini"
    settings.GEMINI_API_KEY = ""

    assert api.get(URL).json()["ai_enabled"] is False


def test_a_stale_token_does_not_break_a_public_call(api: APIClient) -> None:
    for header in ("Token expired-token", "Customer expired-token"):
        assert api.get(URL, HTTP_AUTHORIZATION=header).status_code == 200


def test_only_get_is_allowed(api: APIClient) -> None:
    assert api.post(URL, {}, format="json").status_code == 405


def test_a_trailing_slash_is_not_a_route(api: APIClient) -> None:
    """The contract's paths have no trailing slash (docs/api-conventions.md)."""
    assert api.get(URL + "/").status_code == 404
