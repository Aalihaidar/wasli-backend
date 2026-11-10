"""Request id, ``no-store`` and the size of a request body for the API.

Three small middlewares that wrap every request, so a response that never reaches a view (a
rejected body, a disallowed host) carries the same headers as any other.
"""

import re
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from typing import Final

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

API_PREFIX: Final = "/api/v1/"
REQUEST_ID_HEADER: Final = "X-Request-ID"
# What a client may send as its own request id: 8 to 64 letters, digits and hyphens. Anything
# else is replaced, so a client can never put its own text into a log line.
REQUEST_ID_PATTERN: Final = re.compile(r"[A-Za-z0-9-]{8,64}")

# The id of the request being handled, for its log lines (config/logging_filters.py).
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdMiddleware:
    """Give every request an id, keep it for the log lines and send it back as
    ``X-Request-ID``.

    The id carries no personal data and no position: the app may show it on a "Something went
    wrong" screen and the team finds the request by it. A client's own id is kept only in the
    form of :data:`REQUEST_ID_PATTERN`.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        supplied = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = (
            supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid.uuid4())
        )
        request.request_id = request_id  # type: ignore[attr-defined]
        token = request_id_var.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
        response[REQUEST_ID_HEADER] = request_id
        return response


class NoStoreMiddleware:
    """Send ``Cache-Control: no-store`` on every response under ``/api/v1/``, errors included.

    What the API answers (a customer's chat, an order with a car and a position) must not be
    kept by a browser, a proxy or an app cache.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if request.path.startswith(API_PREFIX):
            response["Cache-Control"] = "no-store"
        return response


def body_limit(path: str) -> tuple[int, str]:
    """The largest body, in bytes, that a request to ``path`` may have, and the error code
    that refuses a larger one."""
    for pattern, limit, code in settings.REQUEST_BODY_LIMITS:
        if re.fullmatch(pattern, path):
            return limit, code
    return settings.REQUEST_BODY_MAX_BYTES, "request_too_large"


class RequestSizeMiddleware:
    """Refuse a request body over the limit before anything reads it: ``400`` with the code
    of the limit (``request_too_large``, or ``audio_too_large`` for a voice upload).

    The check is on ``Content-Length``. A WSGI server hands Django a body only up to that
    length and a request without one has no body to read, so a body cannot grow past the limit
    unseen. The limits are ``REQUEST_BODY_MAX_BYTES`` and ``REQUEST_BODY_LIMITS``.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path.startswith(API_PREFIX):
            limit, code = body_limit(request.path)
            if self._declared_size(request) > limit:
                return JsonResponse(
                    {
                        "type": "client_error",
                        "errors": [
                            {
                                "code": code,
                                "detail": "The request body is too large.",
                                "attr": None,
                            }
                        ],
                    },
                    status=400,
                )
        return self.get_response(request)

    @staticmethod
    def _declared_size(request: HttpRequest) -> int:
        declared = request.headers.get("content-length", "")
        if not declared.isascii() or not declared.isdigit():
            return 0
        return int(declared)
