"""Swagger UI and the live schema: for staff only, bundled, never in production."""

import json
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from config.api_docs import docs_enabled, docs_urlpatterns
from restaurants.tests.factories import make_user
from users.models import User

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.urls("config.tests.docs_urls"),
]

DOCS = "/api/docs/"
SCHEMA = "/api/schema/"
JSON = {"Accept": "application/vnd.oai.openapi+json"}


def _staff() -> User:
    user = make_user("platform-staff")
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return user


@pytest.fixture
def staff_client() -> Client:
    client = Client()
    client.force_login(_staff())
    return client


@pytest.fixture
def user_client() -> Client:
    client = Client()
    client.force_login(make_user("plain-user"))
    return client


# --- who may open them ---------------------------------------------------------------------


@pytest.mark.parametrize("path", [DOCS, SCHEMA])
def test_an_anonymous_visitor_gets_a_404_not_a_redirect(
    client: Client, path: str
) -> None:
    """A redirect to the admin sign-in would show every visitor where the admin is."""
    response = client.get(path)

    assert response.status_code == 404
    assert "Location" not in response


@pytest.mark.parametrize("path", [DOCS, SCHEMA])
def test_a_signed_in_user_who_is_not_staff_gets_a_404(
    user_client: Client, path: str
) -> None:
    assert user_client.get(path).status_code == 404


@pytest.mark.parametrize("path", [DOCS, SCHEMA])
def test_an_inactive_staff_account_gets_a_404(path: str) -> None:
    client = Client()
    user = _staff()
    client.force_login(user)
    user.is_active = False
    user.save(update_fields=["is_active"])

    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", [DOCS, SCHEMA])
def test_an_api_token_does_not_open_the_docs(client: Client, path: str) -> None:
    """The docs are not an API operation: a token is not a staff session."""
    response = client.get(path, headers={"Authorization": "Token anything"})

    assert response.status_code == 404


# --- what staff see ------------------------------------------------------------------------


def test_staff_get_swagger_ui_with_bundled_assets(staff_client: Client) -> None:
    response = staff_client.get(DOCS)

    assert response.status_code == 200
    page = response.content.decode()
    assert "swagger-ui" in page
    assert (
        "/static/drf_spectacular_sidecar/swagger-ui-dist/swagger-ui-bundle.js" in page
    )
    assert "cdn." not in page
    assert "http://" not in page.replace("http://www.w3.org", "")


def test_swagger_ui_is_pointed_at_the_live_schema(staff_client: Client) -> None:
    page = staff_client.get(DOCS).content.decode()

    assert reverse("api-schema") in page
    assert '"persistAuthorization": true' in page


@pytest.mark.parametrize("path", [DOCS, SCHEMA])
def test_the_pages_are_never_cached(staff_client: Client, path: str) -> None:
    cache_control = staff_client.get(path)["Cache-Control"]

    assert "no-store" in cache_control or "no-cache" in cache_control


def test_the_schema_is_served_as_json_and_names_the_project(
    staff_client: Client,
) -> None:
    response = staff_client.get(SCHEMA, headers=JSON)

    document = json.loads(response.content)
    assert response.status_code == 200
    assert document["info"]["title"] == "Wasli API"
    assert document["openapi"].startswith("3.")


def test_the_docs_do_not_describe_themselves(staff_client: Client) -> None:
    document = json.loads(staff_client.get(SCHEMA, headers=JSON).content)

    assert not [
        path
        for path in document["paths"]
        if path.startswith(("/api/docs", "/api/schema"))
    ]


# --- local and staging only ----------------------------------------------------------------


@pytest.mark.parametrize("environment", ["local", "staging"])
def test_local_and_staging_serve_the_docs(settings: Any, environment: str) -> None:
    settings.ENVIRONMENT = environment

    assert docs_enabled() is True
    assert [pattern.name for pattern in docs_urlpatterns()] == [
        "api-schema",
        "api-docs",
    ]


@pytest.mark.parametrize("environment", ["production", "anything-else", ""])
def test_production_and_unknown_environments_serve_no_docs_route(
    settings: Any, environment: str
) -> None:
    settings.ENVIRONMENT = environment

    assert docs_enabled() is False
    assert docs_urlpatterns() == []
