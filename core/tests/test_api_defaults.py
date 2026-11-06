"""The DRF defaults every endpoint inherits: closed by default, paginated, throttled."""

from typing import Any

import pytest
from django.core.cache import cache
from django.urls import path
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework.views import APIView

from config.api_errors import ErrorCode409Enum
from core.pagination import StandardPagination
from users.models import User


class _Private(APIView):  # type: ignore[misc]
    def get(self, request: Request) -> Response:
        return Response({"ok": True})


class _Public(APIView):  # type: ignore[misc]
    permission_classes = [AllowAny]  # noqa: RUF012

    def get(self, request: Request) -> Response:
        return Response({"ok": True})


class _Numbers(APIView):  # type: ignore[misc]
    permission_classes = [AllowAny]  # noqa: RUF012

    def get(self, request: Request) -> Response:
        paginator = StandardPagination()
        page = paginator.paginate_queryset(list(range(250)), request)
        return paginator.get_paginated_response(page)


urlpatterns = [
    path("private/", _Private.as_view()),
    path("public/", _Public.as_view()),
    path("numbers/", _Numbers.as_view()),
]


@pytest.fixture(autouse=True)
def _clean_throttle_cache() -> None:
    cache.clear()


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
@pytest.mark.urls(__name__)
class TestDefaults:
    def test_a_view_is_closed_unless_it_says_otherwise(self, client: APIClient) -> None:
        response = client.get("/private/")

        assert response.status_code == 401
        assert response.json()["errors"][0]["code"] == "not_authenticated"

    def test_a_staff_token_opens_it(self, client: APIClient) -> None:
        user = User.objects.create_user("cashier", "s3cret-pass")
        token = Token.objects.create(user=user)

        response = client.get("/private/", HTTP_AUTHORIZATION=f"Token {token.key}")

        assert response.status_code == 200

    def test_a_bad_token_is_refused(self, client: APIClient) -> None:
        response = client.get("/private/", HTTP_AUTHORIZATION="Token nope")

        assert response.status_code == 401
        assert response.json()["errors"][0]["code"] == "authentication_failed"

    def test_a_public_view_needs_no_login(self, client: APIClient) -> None:
        assert client.get("/public/").status_code == 200

    def test_lists_share_one_envelope_and_page_size(self, client: APIClient) -> None:
        body: dict[str, Any] = client.get("/numbers/").json()

        assert set(body) == {"count", "next", "previous", "results"}
        assert body["count"] == 250
        assert len(body["results"]) == 20

    def test_page_size_is_capped(self, client: APIClient) -> None:
        body = client.get("/numbers/?page_size=1000").json()

        assert len(body["results"]) == 100

    def test_an_anonymous_client_is_throttled_with_the_standard_error(
        self, client: APIClient
    ) -> None:
        for _ in range(60):
            assert client.get("/public/").status_code == 200

        response = client.get("/public/")

        assert response.status_code == 429
        assert response.json()["errors"][0]["code"] == "throttled"


def test_the_409_conflict_codes_are_listed_once() -> None:
    assert "order_invalid_transition" in ErrorCode409Enum.values
