"""The API baseline: request id, no-store, the size of a body and the CORS headers."""

import logging
import re
import uuid
from typing import Any

import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from rest_framework.test import APIClient

from config.logging_filters import RequestIdFilter
from config.middleware import NoStoreMiddleware, request_id_var

pytestmark = pytest.mark.django_db

REQUEST_ID = "X-Request-ID"
CONFIG = "/api/v1/config"
VOICE = "/api/v1/conversations/6f1c3a52-3b8e-4a49-9d1e-5b6a2f0c8e11/voice"


@pytest.fixture
def api() -> APIClient:
    return APIClient()


# --- the request id ---------------------------------------------------------------------------


def test_every_answer_carries_a_generated_request_id(api: APIClient) -> None:
    response = api.get(CONFIG)

    assert str(uuid.UUID(response[REQUEST_ID])) == response[REQUEST_ID]


def test_two_requests_get_two_ids(api: APIClient) -> None:
    assert api.get(CONFIG)[REQUEST_ID] != api.get(CONFIG)[REQUEST_ID]


@pytest.mark.parametrize(
    "own",
    ["12345678", "7c1f0d52-3b8e-4a49-9d1e-5b6a2f0c8e11", "A" * 64, "abc-DEF-123-xyz"],
)
def test_a_well_formed_id_of_the_client_is_kept(api: APIClient, own: str) -> None:
    assert api.get(CONFIG, headers={REQUEST_ID: own})[REQUEST_ID] == own


@pytest.mark.parametrize(
    "own",
    [
        "short",
        "A" * 65,
        "has space in it",
        "line\\nbreak-1234",
        "<script>alert(1)",
        "é" * 10,
    ],
)
def test_a_malformed_id_is_replaced(api: APIClient, own: str) -> None:
    got = api.get(CONFIG, headers={REQUEST_ID: own})[REQUEST_ID]

    assert got != own
    assert str(uuid.UUID(got)) == got


def test_errors_carry_the_id_too(api: APIClient) -> None:
    for response in (api.get("/api/v1/nowhere"), api.get("/api/v1/restaurants/nearby")):
        assert response.status_code in {400, 404}
        assert re.fullmatch(r"[0-9a-f-]{36}", response[REQUEST_ID])


def test_the_id_is_not_left_set_after_the_request(api: APIClient) -> None:
    api.get(CONFIG)

    assert request_id_var.get() == "-"


# --- the log lines ----------------------------------------------------------------------------


def make_record() -> logging.LogRecord:
    return logging.LogRecord("x", logging.INFO, __file__, 1, "message", None, None)


def test_a_log_record_takes_the_id_of_the_running_request() -> None:
    token = request_id_var.set("abc-12345678")
    try:
        record = make_record()
        assert RequestIdFilter().filter(record) is True
    finally:
        request_id_var.reset(token)

    assert record.request_id == "abc-12345678"  # type: ignore[attr-defined]


def test_a_log_record_outside_a_request_shows_a_dash() -> None:
    record = make_record()

    RequestIdFilter().filter(record)

    assert record.request_id == "-"  # type: ignore[attr-defined]


def test_django_error_records_read_the_id_from_their_request() -> None:
    class FakeRequest:
        request_id = "from-the-request"

    record = make_record()
    record.request = FakeRequest()

    RequestIdFilter().filter(record)

    assert record.request_id == "from-the-request"  # type: ignore[attr-defined]


# --- no-store ---------------------------------------------------------------------------------


def test_api_answers_are_never_cached(api: APIClient) -> None:
    assert api.get(CONFIG)["Cache-Control"] == "no-store"
    assert api.get("/api/v1/restaurants/nowhere")["Cache-Control"] == "no-store"
    assert api.get("/api/v1/restaurants/nearby")["Cache-Control"] == "no-store"


def test_nothing_outside_the_api_is_touched() -> None:
    """The middleware sets the header only under /api/v1/: other pages keep their own."""
    middleware = NoStoreMiddleware(lambda request: HttpResponse("page"))

    assert "Cache-Control" not in middleware(RequestFactory().get("/somewhere"))
    assert middleware(RequestFactory().get("/api/v1/x"))["Cache-Control"] == "no-store"


# --- the size of a body -----------------------------------------------------------------------


def test_a_body_over_the_limit_is_refused_before_a_view(
    api: APIClient, settings: Any
) -> None:
    body = b"x" * (settings.REQUEST_BODY_MAX_BYTES + 1)

    response = api.post(CONFIG, data=body, content_type="application/json")

    assert response.status_code == 400
    assert response.json() == {
        "type": "client_error",
        "errors": [
            {
                "code": "request_too_large",
                "detail": "The request body is too large.",
                "attr": None,
            }
        ],
    }
    assert response[REQUEST_ID]
    assert response["Cache-Control"] == "no-store"


def test_a_body_at_the_limit_goes_through(api: APIClient, settings: Any) -> None:
    body = b"x" * settings.REQUEST_BODY_MAX_BYTES

    response = api.post(CONFIG, data=body, content_type="application/json")

    assert (
        response.status_code == 405
    )  # config only answers GET: it got past the size check


def test_a_voice_upload_may_be_larger_and_has_its_own_code(api: APIClient) -> None:
    just_fine = api.post(VOICE, data=b"x" * (5 * 1024 * 1024), content_type="audio/wav")
    too_big = api.post(
        VOICE, data=b"x" * (6 * 1024 * 1024 + 1), content_type="audio/wav"
    )

    assert just_fine.status_code == 404  # no voice route yet, but the size was accepted
    assert too_big.status_code == 400
    assert too_big.json()["errors"][0]["code"] == "audio_too_large"


def test_the_voice_limit_does_not_apply_to_other_paths(api: APIClient) -> None:
    response = api.post(
        "/api/v1/conversations/6f1c3a52-3b8e-4a49-9d1e-5b6a2f0c8e11/messages",
        data=b"x" * (70 * 1024),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "request_too_large"


@pytest.mark.parametrize("declared", ["abc", "-5", "\uff11\uff12\uff13", ""])
def test_a_content_length_that_is_not_a_number_is_ignored(
    api: APIClient, declared: str
) -> None:
    response = api.get(CONFIG, headers={"Content-Length": declared})

    assert response.status_code == 200


def test_the_limit_applies_to_the_api_only(api: APIClient, settings: Any) -> None:
    body = b"x" * (settings.REQUEST_BODY_MAX_BYTES + 1)

    response = api.post("/admin/login/", data=body, content_type="text/plain")

    assert response.status_code != 400 or b"request_too_large" not in response.content


# --- CORS -------------------------------------------------------------------------------------


def test_the_browser_apps_can_read_and_send_the_request_id(
    api: APIClient, settings: Any
) -> None:
    settings.CORS_ALLOWED_ORIGINS = ["https://customer.example.com"]

    answer = api.get(CONFIG, headers={"Origin": "https://customer.example.com"})
    preflight = api.options(
        CONFIG,
        headers={
            "Origin": "https://customer.example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-request-id,authorization",
        },
    )

    assert "X-Request-ID" in answer["Access-Control-Expose-Headers"]
    assert "x-request-id" in preflight["Access-Control-Allow-Headers"]


def test_a_refused_body_still_carries_the_cors_headers(
    api: APIClient, settings: Any
) -> None:
    settings.CORS_ALLOWED_ORIGINS = ["https://customer.example.com"]

    response = api.post(
        CONFIG,
        data=b"x" * (settings.REQUEST_BODY_MAX_BYTES + 1),
        content_type="application/json",
        headers={"Origin": "https://customer.example.com"},
    )

    assert response.status_code == 400
    assert response["Access-Control-Allow-Origin"] == "https://customer.example.com"
