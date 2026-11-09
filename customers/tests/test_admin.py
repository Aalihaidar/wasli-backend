import pytest
from django.test import Client
from django.urls import reverse

from customers.models import Customer, CustomerBlock, CustomerSession
from customers.services import start_session
from customers.tests.factories import PASSWORD, make_customer
from restaurants.tests.factories import make_restaurant
from users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client() -> Client:
    User.objects.create_superuser("owner", PASSWORD, email="owner@example.com")
    client = Client()
    assert client.login(username="owner", password=PASSWORD)
    return client


def test_the_pages_load(admin_client: Client) -> None:
    customer = make_customer()
    session, _ = start_session(customer)
    block = CustomerBlock.objects.create(
        restaurant=make_restaurant("cafe-a"), customer=customer
    )
    pages = [
        reverse("admin:customers_customer_changelist"),
        reverse("admin:customers_customer_add"),
        reverse("admin:customers_customer_change", args=[customer.pk]),
        reverse("admin:customers_customersession_changelist"),
        reverse("admin:customers_customerblock_changelist"),
        reverse("admin:customers_customerblock_add"),
        reverse("admin:customers_customerblock_change", args=[block.pk]),
    ]

    for page in pages:
        assert admin_client.get(page).status_code == 200, page
    assert session.pk


def test_a_session_cannot_be_added_or_edited_by_hand(admin_client: Client) -> None:
    session, _ = start_session(make_customer())

    assert (
        admin_client.get(reverse("admin:customers_customersession_add")).status_code
        == 403
    )
    change = reverse("admin:customers_customersession_change", args=[session.pk])
    # Read-only: the page may show the record but a POST changes nothing.
    admin_client.post(change, {"user_agent": "changed"})
    session.refresh_from_db()
    assert session.user_agent == ""


def test_sessions_can_be_revoked_from_the_list(admin_client: Client) -> None:
    session, _ = start_session(make_customer())

    response = admin_client.post(
        reverse("admin:customers_customersession_changelist"),
        {"action": "revoke_selected", "_selected_action": [str(session.pk)]},
    )

    assert response.status_code == 302
    session.refresh_from_db()
    assert session.is_active is False


def test_a_customer_can_be_blocked_platform_wide(admin_client: Client) -> None:
    customer = make_customer()

    response = admin_client.post(
        reverse("admin:customers_customer_change", args=[customer.pk]),
        {
            "user": str(customer.user.pk),
            "display_name": customer.display_name,
            "locale": "en",
            "is_blocked": "on",
            "vehicles-TOTAL_FORMS": "0",
            "vehicles-INITIAL_FORMS": "0",
            "sessions-TOTAL_FORMS": "0",
            "sessions-INITIAL_FORMS": "0",
        },
    )

    assert response.status_code == 302
    assert Customer.objects.get(pk=customer.pk).is_blocked is True
    assert CustomerSession.objects.count() == 0
