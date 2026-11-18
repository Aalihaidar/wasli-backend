import uuid

import pytest
from django.test import Client
from django.urls import reverse
from pytest_django.fixtures import Settings

from customers.tests.factories import PASSWORD
from orders.models import Order, OrderEvent, OrderItem
from orders.tests.factories import make_event, make_order, make_order_item
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
    order = make_order(
        customer_lat=25.2001, customer_lng=55.2701, location_source="gps"
    )
    make_order_item(order)
    make_event(order)

    pages = [
        reverse("admin:orders_order_changelist"),
        reverse("admin:orders_order_change", args=[order.pk]),
    ]

    for page in pages:
        assert admin_client.get(page).status_code == 200, page


def test_the_list_shows_the_total_in_aed(admin_client: Client) -> None:
    make_order(total_minor=1250, subtotal_minor=1250)

    page = admin_client.get(reverse("admin:orders_order_changelist")).content.decode()

    assert "12.50" in page


def test_the_items_and_history_are_shown(admin_client: Client) -> None:
    order = make_order()
    make_order_item(order, name_en="Karak tea")
    make_event(order, "placed")
    make_event(
        order,
        "accepted",
        from_status="placed",
        actor_type="staff",
        actor_id=uuid.uuid4(),
    )

    page = admin_client.get(
        reverse("admin:orders_order_change", args=[order.pk])
    ).content.decode()

    assert "Karak tea" in page
    assert "accepted" in page.lower()


@pytest.mark.parametrize("environment", ["local", "staging", "production"])
def test_an_order_cannot_be_added_or_changed(
    admin_client: Client, settings: Settings, environment: str
) -> None:
    settings.ENVIRONMENT = environment
    order = make_order()

    assert admin_client.get(reverse("admin:orders_order_add")).status_code == 403
    change = reverse("admin:orders_order_change", args=[order.pk])
    admin_client.post(change, {"status": "delivered", "total_minor": 1})
    order.refresh_from_db()
    assert order.status == "placed"
    assert order.total_minor == 600


@pytest.mark.parametrize("environment", ["local", "staging"])
def test_a_test_order_can_be_deleted_with_its_items_and_history(
    admin_client: Client, settings: Settings, environment: str
) -> None:
    settings.ENVIRONMENT = environment
    order = make_order()
    conversation = order.conversation
    make_order_item(order)
    make_event(order)

    delete = reverse("admin:orders_order_delete", args=[order.pk])
    assert admin_client.get(delete).status_code == 200
    response = admin_client.post(delete, {"post": "yes"})

    assert response.status_code == 302
    assert not Order.objects.filter(pk=order.pk).exists()
    assert OrderItem.objects.count() == 0
    assert OrderEvent.objects.count() == 0
    # The conversation stays, and can now be deleted too.
    conversation.refresh_from_db()
    conversation.delete()


def test_selected_test_orders_can_be_deleted_from_the_list_on_staging(
    admin_client: Client, settings: Settings
) -> None:
    settings.ENVIRONMENT = "staging"
    first, second = make_order(), make_order()

    response = admin_client.post(
        reverse("admin:orders_order_changelist"),
        {
            "action": "delete_selected",
            "_selected_action": [str(first.pk), str(second.pk)],
            "post": "yes",
        },
    )

    assert response.status_code == 302
    assert Order.objects.count() == 0


def test_an_order_cannot_be_deleted_in_production(
    admin_client: Client, settings: Settings
) -> None:
    settings.ENVIRONMENT = "production"
    order = make_order()

    delete = reverse("admin:orders_order_delete", args=[order.pk])
    assert admin_client.get(delete).status_code == 403
    admin_client.post(delete, {"post": "yes"})
    assert Order.objects.filter(pk=order.pk).exists()

    # The bulk action is not offered either, and posting it changes nothing.
    changelist = reverse("admin:orders_order_changelist")
    page = admin_client.get(changelist).content.decode()
    assert "delete_selected" not in page
    admin_client.post(
        changelist,
        {
            "action": "delete_selected",
            "_selected_action": [str(order.pk)],
            "post": "yes",
        },
    )
    assert Order.objects.filter(pk=order.pk).exists()


def test_an_item_and_an_event_cannot_be_changed_from_the_order(
    admin_client: Client,
) -> None:
    order = make_order()
    item = make_order_item(order, name_en="Original")
    event = make_event(order)
    change = reverse("admin:orders_order_change", args=[order.pk])

    admin_client.post(
        change,
        {
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "1",
            "items-0-id": str(item.pk),
            "items-0-name_en": "Changed",
            "items-0-DELETE": "on",
            "events-TOTAL_FORMS": "1",
            "events-INITIAL_FORMS": "1",
            "events-0-id": str(event.pk),
            "events-0-DELETE": "on",
        },
    )

    item.refresh_from_db()
    assert item.name_en == "Original"
    assert OrderItem.objects.filter(pk=item.pk).exists()
    assert OrderEvent.objects.filter(pk=event.pk).exists()


def test_the_coordinates_are_not_shown(admin_client: Client) -> None:
    order = make_order(
        customer_lat=25.2001,
        customer_lng=55.2701,
        location_accuracy_m=12,
        location_source="gps",
        distance_m=85,
    )

    page = admin_client.get(
        reverse("admin:orders_order_change", args=[order.pk])
    ).content.decode()

    assert "25.2001" not in page
    assert "55.2701" not in page
    assert "GPS" in page


def test_the_list_can_be_searched_and_filtered(admin_client: Client) -> None:
    make_order(make_restaurant("cafe-a"), vehicle_plate="A 11111")
    make_order(make_restaurant("cafe-b"), vehicle_plate="B 22222")
    url = reverse("admin:orders_order_changelist")

    found = admin_client.get(url, {"q": "B 22222"}).context["cl"].result_list
    assert [o.restaurant.slug for o in found] == ["cafe-b"]
    placed = admin_client.get(url, {"status": "placed"}).context["cl"].result_list
    assert len(placed) == 2


class TestStatusLabels:
    @pytest.mark.parametrize(
        ("status", "kind", "text"),
        [
            ("placed", "warn", "Placed"),
            ("accepted", "info", "Accepted"),
            ("ready", "ok", "Ready"),
            ("delivered", "ok", "Delivered"),
            ("rejected", "bad", "Rejected"),
            ("not_found", "bad", "Car not found"),
            ("no_show", "bad", "No-show"),
            ("cancelled", "muted", "Cancelled"),
        ],
    )
    def test_each_status_has_its_colour(
        self, admin_client: Client, status: str, kind: str, text: str
    ) -> None:
        if status == "rejected":
            make_order(status=status, rejection_reason_code="too_busy")
        else:
            make_order(status=status)

        page = admin_client.get(
            reverse("admin:orders_order_changelist")
        ).content.decode()

        assert f'<span class="wasli-badge wasli-badge--{kind}">{text}</span>' in page

    def test_the_status_filter_still_works(self, admin_client: Client) -> None:
        make_order(status="accepted")

        page = admin_client.get(
            reverse("admin:orders_order_changelist") + "?status__exact=placed"
        ).content.decode()

        assert "wasli-badge--info" not in page

    def test_the_order_number_is_the_link(self, admin_client: Client) -> None:
        order = make_order()

        page = admin_client.get(
            reverse("admin:orders_order_changelist")
        ).content.decode()

        assert reverse("admin:orders_order_change", args=[order.pk]) in page
