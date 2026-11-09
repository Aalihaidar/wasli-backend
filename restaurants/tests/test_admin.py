import pytest
from django.test import Client
from django.urls import reverse

from core.permissions import Role
from restaurants.models import Restaurant, StaffMembership
from restaurants.tests.factories import PASSWORD, make_lot, make_member, make_restaurant
from users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client() -> Client:
    User.objects.create_superuser("owner", PASSWORD, email="owner@example.com")
    client = Client()
    assert client.login(username="owner", password=PASSWORD)
    return client


def test_the_pages_load(admin_client: Client) -> None:
    restaurant = make_restaurant()
    member = make_member(restaurant, "sara", Role.ADMIN)
    pages = [
        reverse("admin:restaurants_parkinglot_changelist"),
        reverse("admin:restaurants_parkinglot_add"),
        reverse(
            "admin:restaurants_parkinglot_change", args=[restaurant.parking_lot.pk]
        ),
        reverse("admin:restaurants_restaurant_changelist"),
        reverse("admin:restaurants_restaurant_add"),
        reverse("admin:restaurants_restaurant_change", args=[restaurant.pk]),
        reverse("admin:restaurants_staffmembership_changelist"),
        reverse("admin:restaurants_staffmembership_add"),
        reverse("admin:restaurants_staffmembership_change", args=[member.pk]),
    ]

    for page in pages:
        assert admin_client.get(page).status_code == 200, page


def test_the_restaurant_list_shows_the_demo_flag_as_a_filter(
    admin_client: Client,
) -> None:
    make_restaurant("real-cafe")
    make_restaurant("fake-cafe", is_demo=True)

    url = reverse("admin:restaurants_restaurant_changelist")
    only_demo = admin_client.get(url, {"is_demo__exact": "1"})

    assert [r.slug for r in only_demo.context["cl"].result_list] == ["fake-cafe"]


def test_a_restaurant_can_be_added_in_the_admin(admin_client: Client) -> None:
    lot = make_lot()

    response = admin_client.post(
        reverse("admin:restaurants_restaurant_add"),
        {
            "slug": "new-cafe",
            "name_en": "New Cafe",
            "name_ar": "مقهى جديد",
            "is_active": "on",
            "parking_lot": str(lot.pk),
            "latitude": "25.2",
            "longitude": "55.27",
            "default_eta_minutes": "10",
            "subscription_status": "trial",
            "accepts_cash": "on",
            "timezone": "Asia/Dubai",
            # empty inline formsets
            "restaurants_staffmembership_set-TOTAL_FORMS": "0",
            "restaurants_staffmembership_set-INITIAL_FORMS": "0",
            "restaurants_restaurantmenuimage_set-TOTAL_FORMS": "0",
            "restaurants_restaurantmenuimage_set-INITIAL_FORMS": "0",
        },
    )

    assert response.status_code == 302
    assert Restaurant.objects.filter(slug="new-cafe").exists()


def test_a_restaurant_cannot_be_deleted_in_the_admin(admin_client: Client) -> None:
    restaurant = make_restaurant()

    response = admin_client.post(
        reverse("admin:restaurants_restaurant_delete", args=[restaurant.pk]),
        {"post": "yes"},
    )

    assert response.status_code == 403
    assert Restaurant.objects.filter(pk=restaurant.pk).exists()


def test_the_membership_list_has_no_bulk_delete(admin_client: Client) -> None:
    make_member(make_restaurant(), "sara", Role.ADMIN)

    response = admin_client.get(reverse("admin:restaurants_staffmembership_changelist"))

    # With no actions at all there is no action form, so no bulk delete either.
    assert response.context["action_form"] is None


def test_the_last_admin_cannot_be_deactivated_in_the_admin(
    admin_client: Client,
) -> None:
    admin = make_member(make_restaurant(), "boss", Role.ADMIN)

    response = admin_client.post(
        reverse("admin:restaurants_staffmembership_change", args=[admin.pk]),
        {
            "user": str(admin.user.pk),
            "restaurant": str(admin.restaurant.pk),
            "role": "admin",
        },
    )

    assert response.status_code == 200  # the form is shown again with the error
    admin.refresh_from_db()
    assert admin.is_active is True
    assert StaffMembership.objects.filter(pk=admin.pk, is_active=True).exists()
