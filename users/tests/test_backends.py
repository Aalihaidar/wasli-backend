import pytest
from django.contrib.auth import authenticate
from django.test import Client

from users.models import User

PASSWORD = "s3cret-pass"


@pytest.fixture
def account() -> User:
    return User.objects.create_user(
        "sara.ahmed", PASSWORD, email="sara@example.com", phone="+971501234567"
    )


@pytest.mark.django_db
class TestIdentifierBackend:
    @pytest.mark.parametrize(
        "value",
        [
            "sara.ahmed",
            "  SARA.Ahmed ",
            "sara@example.com",
            "Sara@Example.COM",
            "+971501234567",
            "050 123 4567",
            "0501234567",
        ],
    )
    def test_signs_in_with_username_email_or_phone(
        self,
        account: User,
        value: str,
    ) -> None:
        assert authenticate(username=value, password=PASSWORD) == account

    def test_wrong_password_is_rejected(self, account: User) -> None:
        assert authenticate(username="sara.ahmed", password="wrong") is None

    @pytest.mark.parametrize(
        "value", ["nobody", "nobody@example.com", "+971509999999", "", "123"]
    )
    def test_unknown_account_is_rejected(self, account: User, value: str) -> None:
        assert authenticate(username=value, password=PASSWORD) is None

    def test_inactive_account_is_rejected(self, account: User) -> None:
        account.is_active = False
        account.save()

        assert authenticate(username="sara.ahmed", password=PASSWORD) is None

    def test_account_without_a_usable_password_is_rejected(self) -> None:
        User.objects.create_user("demo-cashier")

        assert authenticate(username="demo-cashier", password="") is None

    def test_a_phone_never_matches_a_username(self) -> None:
        # Usernames start with a letter, so the digits can only be read as a phone number.
        User.objects.create_user("sara", PASSWORD)

        assert authenticate(username="0501234567", password=PASSWORD) is None

    def test_permissions_still_work(self) -> None:
        owner = User.objects.create_superuser(
            "owner", PASSWORD, email="owner@example.com"
        )

        assert owner.has_perm("users.view_user")


@pytest.mark.django_db
class TestAdminLogin:
    def test_the_platform_team_signs_in_to_the_admin_with_an_email(self) -> None:
        User.objects.create_superuser("owner", PASSWORD, email="owner@example.com")
        client = Client()

        assert client.login(username="owner@example.com", password=PASSWORD)
        assert client.get("/admin/").status_code == 200

    def test_a_non_staff_user_cannot_use_the_admin(self, account: User) -> None:
        client = Client()

        assert client.login(username="sara.ahmed", password=PASSWORD)
        response = client.get("/admin/")
        assert response.status_code == 302
        assert "/admin/login/" in response["Location"]
