import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

User = get_user_model()


@pytest.mark.django_db
class TestUserManager:
    def test_create_user_normalises_the_email(self) -> None:
        user = User.objects.create_user("  Cashier@Example.COM ", "s3cret-pass")

        assert user.email == "cashier@example.com"
        assert user.check_password("s3cret-pass")
        assert not user.is_staff
        assert not user.is_superuser
        assert user.is_active

    def test_user_gets_a_uuid_primary_key(self) -> None:
        user = User.objects.create_user("a@example.com", "s3cret-pass")

        assert user.pk.version == 4

    def test_create_user_without_password_is_unusable(self) -> None:
        user = User.objects.create_user("demo-cashier@example.com")

        assert not user.has_usable_password()

    def test_create_user_requires_an_email(self) -> None:
        with pytest.raises(ValueError, match="email"):
            User.objects.create_user("  ", "s3cret-pass")

    def test_create_superuser_sets_the_admin_flags(self) -> None:
        user = User.objects.create_superuser("owner@example.com", "s3cret-pass")

        assert user.is_staff
        assert user.is_superuser

    def test_create_superuser_rejects_a_contradicting_flag(self) -> None:
        with pytest.raises(ValueError, match="is_staff"):
            User.objects.create_superuser(
                "owner@example.com", "s3cret-pass", is_staff=False
            )

    def test_email_is_unique_regardless_of_case(self) -> None:
        User.objects.create_user("a@example.com", "s3cret-pass")

        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.create_user("A@Example.com", "s3cret-pass")


@pytest.mark.django_db
class TestUser:
    def test_str_and_names(self) -> None:
        user = User.objects.create_user(
            "a@example.com", "s3cret-pass", full_name="Sara Ahmed"
        )

        assert str(user) == "a@example.com"
        assert user.get_full_name() == "Sara Ahmed"

    def test_name_falls_back_to_the_email(self) -> None:
        user = User.objects.create_user("a@example.com", "s3cret-pass")

        assert user.get_full_name() == "a@example.com"
        assert user.get_short_name() == "a@example.com"
