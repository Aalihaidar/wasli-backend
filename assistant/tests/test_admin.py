import pytest
from django.test import Client
from django.urls import reverse

from assistant.models import AICallLog
from assistant.tests.test_models import make_call
from customers.tests.factories import PASSWORD
from users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client() -> Client:
    User.objects.create_superuser("owner", PASSWORD, email="owner@example.com")
    client = Client()
    assert client.login(username="owner", password=PASSWORD)
    return client


def test_the_pages_load(admin_client: Client) -> None:
    call = make_call()

    assert (
        admin_client.get(reverse("admin:assistant_aicalllog_changelist")).status_code
        == 200
    )
    assert (
        admin_client.get(
            reverse("admin:assistant_aicalllog_change", args=[call.pk])
        ).status_code
        == 200
    )


def test_a_call_cannot_be_added_changed_or_deleted(admin_client: Client) -> None:
    call = make_call()

    assert admin_client.get(reverse("admin:assistant_aicalllog_add")).status_code == 403
    admin_client.post(
        reverse("admin:assistant_aicalllog_change", args=[call.pk]),
        {"outcome": "error"},
    )
    call.refresh_from_db()
    assert call.outcome == "ok"

    delete = reverse("admin:assistant_aicalllog_delete", args=[call.pk])
    assert admin_client.get(delete).status_code == 403
    admin_client.post(delete, {"post": "yes"})
    assert AICallLog.objects.filter(pk=call.pk).exists()


def test_the_list_can_be_filtered_by_outcome(admin_client: Client) -> None:
    make_call(outcome="ok")
    make_call(outcome="timeout")

    found = (
        admin_client.get(
            reverse("admin:assistant_aicalllog_changelist"), {"outcome": "timeout"}
        )
        .context["cl"]
        .result_list
    )

    assert [c.outcome for c in found] == ["timeout"]


@pytest.mark.parametrize(
    ("outcome", "kind", "text"),
    [
        ("ok", "ok", "OK"),
        ("timeout", "warn", "Timeout"),
        ("rate_limited", "warn", "Rate limited"),
        ("budget_exceeded", "warn", "Daily budget exceeded"),
        ("invalid_output", "bad", "Invalid output"),
        ("error", "bad", "Error"),
    ],
)
def test_an_outcome_has_its_colour(
    admin_client: Client, outcome: str, kind: str, text: str
) -> None:
    from assistant.models import AICallLog

    AICallLog.objects.create(
        provider="fake", purpose="classify_reply", input_kind="text", outcome=outcome
    )

    page = admin_client.get(
        reverse("admin:assistant_aicalllog_changelist")
    ).content.decode()

    assert f'<span class="wasli-badge wasli-badge--{kind}">{text}</span>' in page
