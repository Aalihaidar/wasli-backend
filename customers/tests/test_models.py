import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from core.permissions import Role
from customers.models import Customer, CustomerBlock, CustomerSession, Vehicle
from customers.tests.factories import PASSWORD, make_customer
from restaurants.models import StaffMembership
from restaurants.tests.factories import make_member, make_restaurant
from users.models import User

pytestmark = pytest.mark.django_db


class TestCustomer:
    def test_defaults(self) -> None:
        customer = make_customer()

        assert customer.locale == "en"
        assert customer.is_blocked is False
        assert customer.last_seen_at is None
        assert str(customer) == "Sara Example"
        assert customer.pk.version == 4

    def test_the_name_falls_back_to_the_account(self) -> None:
        user = User.objects.create_user(None, PASSWORD, email="omar@example.com")

        assert "omar@example.com" in str(Customer.objects.create(user=user))

    def test_a_user_has_one_profile(self) -> None:
        customer = make_customer()

        with pytest.raises(IntegrityError), transaction.atomic():
            Customer.objects.create(user=customer.user)

    def test_the_profile_is_reachable_from_the_user(self) -> None:
        customer = make_customer()

        assert customer.user.customer == customer  # type: ignore[attr-defined]

    def test_the_locale_is_one_of_the_two_languages(self) -> None:
        customer = make_customer()
        customer.locale = "fr"

        with pytest.raises(ValidationError) as error:
            customer.full_clean()
        assert "locale" in error.value.message_dict

    def test_a_platform_superuser_cannot_be_a_customer(self) -> None:
        superuser = User.objects.create_superuser(
            "owner", PASSWORD, email="owner@example.com"
        )

        with pytest.raises(ValidationError) as error:
            Customer(user=superuser).full_clean()
        assert "user" in error.value.message_dict
        with pytest.raises(ValidationError):
            Customer.objects.create(user=superuser)

    def test_a_staff_user_cannot_be_a_customer(self) -> None:
        user = User.objects.create_user("clerk", PASSWORD, is_staff=True)

        with pytest.raises(ValidationError):
            Customer.objects.create(user=user)

    def test_a_restaurant_member_cannot_be_a_customer(self) -> None:
        member = make_member(make_restaurant("cafe-a"), "sara", Role.CASHIER)

        with pytest.raises(ValidationError) as error:
            Customer.objects.create(user=member.user)
        assert "user" in error.value.message_dict
        assert not Customer.objects.exists()

    def test_a_customer_cannot_become_restaurant_staff(self) -> None:
        user = User.objects.create_user("sara", PASSWORD, email="sara@example.com")
        Customer.objects.create(user=user)
        restaurant = make_restaurant("cafe-a")

        with pytest.raises(ValidationError) as error:
            StaffMembership.objects.create(
                restaurant=restaurant, user=user, role="cashier"
            )
        assert "user" in error.value.message_dict
        assert not StaffMembership.objects.exists()

    def test_a_customer_keeps_their_user(self) -> None:
        customer = make_customer()

        with pytest.raises(ProtectedError):
            customer.user.delete()


class TestCustomerSession:
    def test_it_is_active_until_revoked(self) -> None:
        session = CustomerSession.objects.create(
            customer=make_customer(), token_hash="a" * 64
        )

        assert session.is_active is True

    def test_the_token_hash_is_unique(self) -> None:
        customer = make_customer()
        CustomerSession.objects.create(customer=customer, token_hash="a" * 64)

        with pytest.raises(IntegrityError), transaction.atomic():
            CustomerSession.objects.create(customer=customer, token_hash="a" * 64)

    def test_there_is_no_field_that_could_hold_the_token(self) -> None:
        names = {field.name for field in CustomerSession._meta.get_fields()}

        assert "token" not in names
        assert "token_hash" in names


class TestVehicle:
    def test_a_customer_has_a_plate_once(self) -> None:
        customer = make_customer()
        Vehicle.objects.create(customer=customer, plate="A 12345")

        with pytest.raises(IntegrityError), transaction.atomic():
            Vehicle.objects.create(customer=customer, plate="A 12345")

    def test_two_customers_can_have_the_same_plate(self) -> None:
        Vehicle.objects.create(customer=make_customer("a@example.com"), plate="A 1")
        Vehicle.objects.create(customer=make_customer("b@example.com"), plate="A 1")

        assert Vehicle.objects.count() == 2


class TestCustomerBlock:
    def test_a_restaurant_blocks_a_customer_once(self) -> None:
        restaurant, customer = make_restaurant("cafe-a"), make_customer()
        CustomerBlock.objects.create(restaurant=restaurant, customer=customer)

        with pytest.raises(IntegrityError), transaction.atomic():
            CustomerBlock.objects.create(restaurant=restaurant, customer=customer)

    def test_blocks_are_scoped_to_their_restaurant(self) -> None:
        a, b = make_restaurant("cafe-a"), make_restaurant("cafe-b")
        customer = make_customer()
        block_a = CustomerBlock.objects.create(restaurant=a, customer=customer)
        CustomerBlock.objects.create(restaurant=b, customer=customer)

        assert list(CustomerBlock.objects.for_restaurant(a)) == [block_a]
