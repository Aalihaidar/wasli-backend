import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction

from users.models import User


@pytest.mark.django_db
class TestUserManager:
    def test_create_user_with_a_username(self) -> None:
        user = User.objects.create_user("  Cashier.One ", "s3cret-pass")

        assert user.username == "cashier.one"
        assert user.email is None
        assert user.phone is None
        assert user.check_password("s3cret-pass")
        assert not user.is_staff
        assert not user.is_superuser
        assert user.is_active
        assert not user.must_change_password

    def test_user_gets_a_uuid_primary_key(self) -> None:
        user = User.objects.create_user("sara", "s3cret-pass")

        assert user.pk.version == 4

    def test_create_user_without_password_is_unusable(self) -> None:
        user = User.objects.create_user("demo-cashier")

        assert not user.has_usable_password()

    def test_create_user_with_only_an_email(self) -> None:
        user = User.objects.create_user(
            email="  Sara@Example.COM ", password="s3cret-pass"
        )

        assert user.email == "sara@example.com"
        assert user.username is None

    def test_create_user_with_only_a_phone_stores_the_international_form(self) -> None:
        user = User.objects.create_user(phone="050 123 4567", password="s3cret-pass")

        assert user.phone == "+971501234567"
        assert user.username is None
        assert user.email is None

    def test_create_user_requires_an_identifier(self) -> None:
        with pytest.raises(
            ValidationError, match="username, an email address or a phone"
        ):
            User.objects.create_user("  ", "s3cret-pass")

    def test_blank_identifiers_are_stored_as_null_never_empty(self) -> None:
        User.objects.create_user("sara", "s3cret-pass", email="  ", phone="")
        User.objects.create_user("omar", "s3cret-pass", email="", phone="  ")

        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from users_user where email = '' or phone = '' or username = ''"
            )
            assert cursor.fetchone() == (0,)
        assert User.objects.filter(email__isnull=True, phone__isnull=True).count() == 2

    def test_save_converts_a_blank_identifier_to_null(self) -> None:
        user = User(username="sara", email="", phone=" ")
        user.save()

        user.refresh_from_db()
        assert user.email is None
        assert user.phone is None

    def test_database_rejects_an_empty_string_identifier(self) -> None:
        user = User.objects.create_user("sara", "s3cret-pass")

        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=user.pk).update(email="")

    def test_database_rejects_a_user_without_any_identifier(self) -> None:
        user = User.objects.create_user("sara", "s3cret-pass")

        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=user.pk).update(username=None)

    @pytest.mark.parametrize(
        "username",
        ["ab", "1sara", "_sara", "sa ra", "sara@home", "s" * 31, "سارة"],
    )
    def test_create_user_rejects_a_bad_username(self, username: str) -> None:
        with pytest.raises(ValidationError, match="username"):
            User.objects.create_user(username, "s3cret-pass")

    def test_create_user_rejects_a_bad_phone(self) -> None:
        with pytest.raises(ValidationError, match="phone"):
            User.objects.create_user("sara", "s3cret-pass", phone="12345")

    def test_create_user_rejects_a_bad_email(self) -> None:
        with pytest.raises(ValidationError, match="email"):
            User.objects.create_user("sara", "s3cret-pass", email="not-an-email")

    def test_create_superuser_sets_the_admin_flags(self) -> None:
        user = User.objects.create_superuser(
            "owner", "s3cret-pass", email="owner@example.com"
        )

        assert user.is_staff
        assert user.is_superuser
        assert user.email == "owner@example.com"

    def test_create_superuser_requires_an_email(self) -> None:
        with pytest.raises(ValueError, match="email"):
            User.objects.create_superuser("owner", "s3cret-pass")

    def test_create_superuser_rejects_a_contradicting_flag(self) -> None:
        with pytest.raises(ValueError, match="is_staff"):
            User.objects.create_superuser(
                "owner", "s3cret-pass", email="owner@example.com", is_staff=False
            )

    def test_createsuperuser_command_asks_for_a_username_and_an_email(self) -> None:
        call_command(
            "createsuperuser",
            interactive=False,
            username="Owner",
            email="Owner@Example.com",
            verbosity=0,
        )

        user = User.objects.get(username="owner")
        assert user.is_superuser
        assert user.is_staff
        assert user.email == "owner@example.com"

    def test_get_by_natural_key_ignores_case(self) -> None:
        user = User.objects.create_user("sara", "s3cret-pass")

        assert User.objects.get_by_natural_key("SARA") == user


@pytest.mark.django_db
class TestUniqueness:
    def test_username_is_unique_regardless_of_case(self) -> None:
        User.objects.create_user("sara", "s3cret-pass")

        with pytest.raises(ValidationError, match="username"):
            User.objects.create_user("Sara", "s3cret-pass")

    def test_email_is_unique_regardless_of_case(self) -> None:
        User.objects.create_user("sara", "s3cret-pass", email="a@example.com")

        with pytest.raises(ValidationError, match="email"):
            User.objects.create_user("omar", "s3cret-pass", email="A@Example.com")

    def test_phone_is_unique_across_spellings(self) -> None:
        User.objects.create_user("sara", "s3cret-pass", phone="+971501234567")

        with pytest.raises(ValidationError, match="phone"):
            User.objects.create_user("omar", "s3cret-pass", phone="050-123-4567")

    def test_database_enforces_the_unique_email_below_the_model(self) -> None:
        User.objects.create_user("sara", "s3cret-pass", email="a@example.com")

        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.create(username="omar", email="a@example.com")

    def test_many_users_can_leave_an_identifier_unset(self) -> None:
        User.objects.create_user("sara", "s3cret-pass")
        User.objects.create_user("omar", "s3cret-pass")

        assert User.objects.filter(email__isnull=True).count() == 2


@pytest.mark.django_db
class TestUser:
    def test_str_prefers_username_then_email_then_phone(self) -> None:
        assert (
            str(User.objects.create_user("sara", "s3cret-pass", email="a@example.com"))
            == "sara"
        )
        assert str(User.objects.create_user(email="b@example.com")) == "b@example.com"
        assert str(User.objects.create_user(phone="+971501234567")) == "+971501234567"

    def test_names(self) -> None:
        user = User.objects.create_user("sara", "s3cret-pass", full_name="Sara Ahmed")

        assert user.get_full_name() == "Sara Ahmed"
        assert user.get_short_name() == "Sara Ahmed"

    def test_name_falls_back_to_the_identifier(self) -> None:
        user = User.objects.create_user("sara", "s3cret-pass")

        assert user.get_full_name() == "sara"
        assert user.get_short_name() == "sara"

    def test_verification_fields_start_empty(self) -> None:
        user = User.objects.create_user("sara", "s3cret-pass")

        assert user.email_verified_at is None
        assert user.phone_verified_at is None
