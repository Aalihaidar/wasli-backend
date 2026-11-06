import pytest
from django.test import Client
from django.urls import reverse

from users.models import User

PASSWORD = "s3cret-pass-4-tests"


@pytest.fixture
def admin_client() -> Client:
    User.objects.create_superuser("owner", PASSWORD, email="owner@example.com")
    client = Client()
    assert client.login(username="owner", password=PASSWORD)
    return client


def _add_form(**values: str) -> dict[str, str]:
    return {
        "username": "",
        "email": "",
        "phone": "",
        "full_name": "",
        "usable_password": "true",
        "password1": PASSWORD,
        "password2": PASSWORD,
        **values,
    }


@pytest.mark.django_db
class TestUserAdmin:
    def test_pages_load(self, admin_client: Client) -> None:
        user = User.objects.create_user("sara", PASSWORD)

        assert (
            admin_client.get(reverse("admin:users_user_changelist")).status_code == 200
        )
        assert admin_client.get(reverse("admin:users_user_add")).status_code == 200
        assert (
            admin_client.get(
                reverse("admin:users_user_change", args=[user.pk])
            ).status_code
            == 200
        )

    def test_add_a_restaurant_account_with_only_a_username(
        self, admin_client: Client
    ) -> None:
        response = admin_client.post(
            reverse("admin:users_user_add"), _add_form(username="Cashier.One")
        )

        assert response.status_code == 302
        user = User.objects.get(username="cashier.one")
        assert user.email is None
        assert user.phone is None
        assert user.check_password(PASSWORD)

    def test_add_stores_the_phone_in_international_form(
        self, admin_client: Client
    ) -> None:
        response = admin_client.post(
            reverse("admin:users_user_add"), _add_form(phone="050 123 4567")
        )

        assert response.status_code == 302
        assert User.objects.get(phone="+971501234567").username is None

    def test_add_without_any_identifier_is_rejected(self, admin_client: Client) -> None:
        before = User.objects.count()

        response = admin_client.post(reverse("admin:users_user_add"), _add_form())

        assert response.status_code == 200
        assert User.objects.count() == before

    def test_add_with_a_duplicate_username_ignoring_case_is_rejected(
        self, admin_client: Client
    ) -> None:
        User.objects.create_user("sara", PASSWORD)
        before = User.objects.count()

        response = admin_client.post(
            reverse("admin:users_user_add"), _add_form(username="SARA")
        )

        assert response.status_code == 200
        assert User.objects.count() == before

    def test_change_keeps_blank_identifiers_null(self, admin_client: Client) -> None:
        user = User.objects.create_user("sara", PASSWORD, full_name="Sara")

        response = admin_client.post(
            reverse("admin:users_user_change", args=[user.pk]),
            {
                "username": "sara",
                "email": "",
                "phone": "",
                "password": user.password,
                "full_name": "Sara Ahmed",
                "is_active": "on",
                "last_login_0": "",
                "last_login_1": "",
            },
        )

        assert response.status_code == 302
        user.refresh_from_db()
        assert user.full_name == "Sara Ahmed"
        assert user.email is None
        assert user.phone is None
