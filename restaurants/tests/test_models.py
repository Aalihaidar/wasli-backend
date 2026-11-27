import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from core.permissions import Permission, Role, role_has_permission
from restaurants.models import (
    RestaurantMenuImage,
    StaffMembership,
)
from restaurants.tests.factories import make_member, make_restaurant
from users.models import User

pytestmark = pytest.mark.django_db


class TestRestaurant:
    def test_defaults(self) -> None:
        restaurant = make_restaurant()

        assert restaurant.is_active is True
        assert restaurant.is_demo is False
        assert restaurant.currency == "AED"
        assert restaurant.subscription_status == "trial"
        assert restaurant.next_order_number == 1
        assert restaurant.accepts_cash is True
        assert restaurant.accepts_card is False
        assert str(restaurant) == "Cafe One"

    def test_the_slug_is_unique(self) -> None:
        make_restaurant("cafe-one")

        with pytest.raises(IntegrityError):
            make_restaurant("cafe-one")

    @pytest.mark.parametrize(
        "slug", ["Cafe", "cafe_one", "cafe--one", "-cafe", "cafe-", "caf é"]
    )
    def test_a_bad_slug_is_rejected(self, slug: str) -> None:
        restaurant = make_restaurant("valid-slug")
        restaurant.slug = slug

        with pytest.raises(ValidationError) as error:
            restaurant.full_clean()
        assert "slug" in error.value.message_dict

    @pytest.mark.parametrize("colour", ["#1A73E8", "#abcdef", ""])
    def test_a_valid_brand_colour(self, colour: str) -> None:
        restaurant = make_restaurant()
        restaurant.brand_colour = colour

        restaurant.full_clean()

    @pytest.mark.parametrize("colour", ["red", "#12345", "1A73E8", "#GGGGGG"])
    def test_a_bad_brand_colour_is_rejected(self, colour: str) -> None:
        restaurant = make_restaurant()
        restaurant.brand_colour = colour

        with pytest.raises(ValidationError) as error:
            restaurant.full_clean()
        assert "brand_colour" in error.value.message_dict

    def test_the_service_distance_is_optional(self) -> None:
        restaurant = make_restaurant()

        restaurant.full_clean()

        assert restaurant.service_radius_m is None

    def test_a_service_distance_can_be_set(self) -> None:
        restaurant = make_restaurant("gulf-food", service_radius_m=300)

        restaurant.full_clean()
        restaurant.refresh_from_db()

        assert restaurant.service_radius_m == 300

    @pytest.mark.parametrize("value", [0, -5])
    def test_the_service_distance_must_be_positive_when_given(self, value: int) -> None:
        restaurant = make_restaurant()
        restaurant.service_radius_m = value

        with pytest.raises(ValidationError) as error:
            restaurant.full_clean()
        assert "service_radius_m" in error.value.message_dict


class TestStaffMembership:
    def test_a_member_has_a_role_and_is_active_by_default(self) -> None:
        member = make_member(make_restaurant(), "sara", Role.CASHIER)

        assert member.role == "cashier"
        assert member.is_active is True

    def test_a_user_belongs_to_a_restaurant_once(self) -> None:
        restaurant = make_restaurant()
        member = make_member(restaurant, "sara")

        with pytest.raises(IntegrityError):
            StaffMembership.objects.create(
                restaurant=restaurant, user=member.user, role="admin"
            )

    def test_one_person_can_belong_to_two_restaurants(self) -> None:
        member = make_member(make_restaurant("cafe-one"), "sara")

        StaffMembership.objects.create(
            restaurant=make_restaurant("cafe-two"), user=member.user, role="cashier"
        )

        assert StaffMembership.objects.filter(user=member.user).count() == 2

    def test_a_restaurant_account_needs_a_username(self) -> None:
        user = User.objects.create_user(
            None, "pw-for-tests-1", email="sara@example.com"
        )
        member = StaffMembership(
            restaurant=make_restaurant(), user=user, role="cashier"
        )

        with pytest.raises(ValidationError) as error:
            member.full_clean()
        assert "user" in error.value.message_dict
        with pytest.raises(ValidationError):
            member.save()
        assert not StaffMembership.objects.exists()

    def test_an_unknown_role_is_rejected(self) -> None:
        member = make_member(make_restaurant(), "sara")
        member.role = "owner"

        with pytest.raises(ValidationError) as error:
            member.full_clean()
        assert "role" in error.value.message_dict


class TestLastAdmin:
    def test_the_only_admin_cannot_be_demoted(self) -> None:
        admin = make_member(make_restaurant(), "boss", Role.ADMIN)
        admin.role = Role.CASHIER.value

        with pytest.raises(ValidationError):
            admin.save()
        admin.refresh_from_db()
        assert admin.role == "admin"

    def test_the_only_admin_cannot_be_deactivated(self) -> None:
        admin = make_member(make_restaurant(), "boss", Role.ADMIN)
        admin.is_active = False

        with pytest.raises(ValidationError):
            admin.save()
        admin.refresh_from_db()
        assert admin.is_active is True

    def test_the_only_admin_cannot_be_removed(self) -> None:
        admin = make_member(make_restaurant(), "boss", Role.ADMIN)

        with pytest.raises(ValidationError):
            admin.delete()
        assert StaffMembership.objects.filter(pk=admin.pk).exists()

    def test_the_form_check_also_blocks_the_last_admin(self) -> None:
        admin = make_member(make_restaurant(), "boss", Role.ADMIN)
        admin.is_active = False

        with pytest.raises(ValidationError):
            admin.full_clean()

    def test_an_admin_can_step_down_when_another_admin_is_active(self) -> None:
        restaurant = make_restaurant()
        first = make_member(restaurant, "boss", Role.ADMIN)
        make_member(restaurant, "deputy", Role.ADMIN)

        first.role = Role.CASHIER.value
        first.save()

        first.refresh_from_db()
        assert first.role == "cashier"

    def test_a_deactivated_admin_does_not_count_as_another_admin(self) -> None:
        restaurant = make_restaurant()
        first = make_member(restaurant, "boss", Role.ADMIN)
        make_member(restaurant, "retired", Role.ADMIN, is_active=False)
        first.is_active = False

        with pytest.raises(ValidationError):
            first.save()

    def test_another_restaurants_admin_does_not_count(self) -> None:
        first = make_member(make_restaurant("cafe-one"), "boss", Role.ADMIN)
        make_member(make_restaurant("cafe-two"), "other", Role.ADMIN)
        first.is_active = False

        with pytest.raises(ValidationError):
            first.save()

    def test_a_cashier_can_be_deactivated_and_reactivated(self) -> None:
        restaurant = make_restaurant()
        make_member(restaurant, "boss", Role.ADMIN)
        cashier = make_member(restaurant, "sara", Role.CASHIER)

        cashier.is_active = False
        cashier.save()
        cashier.is_active = True
        cashier.save()

        cashier.refresh_from_db()
        assert cashier.is_active is True

    def test_a_deactivated_admin_can_be_reactivated(self) -> None:
        restaurant = make_restaurant()
        make_member(restaurant, "boss", Role.ADMIN)
        retired = make_member(restaurant, "retired", Role.ADMIN, is_active=False)

        retired.is_active = True
        retired.save()

        retired.refresh_from_db()
        assert retired.is_active is True

    def test_the_first_admin_of_a_restaurant_can_be_added(self) -> None:
        member = make_member(make_restaurant(), "boss", Role.ADMIN)

        assert member.role == "admin"


class TestEnglishOnlyRestaurant:
    def test_the_arabic_name_and_caption_can_be_left_empty(self) -> None:
        restaurant = make_restaurant("gulf-food", name_ar="")

        restaurant.full_clean()

        assert restaurant.name_ar == ""
        assert restaurant.name_ar_display == "Gulf Food"

    def test_a_menu_image_caption_falls_back_to_english(self) -> None:
        restaurant = make_restaurant("gulf-food", name_ar="")
        image = RestaurantMenuImage(
            restaurant=restaurant, image="x.jpg", caption_en="Main menu"
        )

        image.full_clean(exclude=["image"])

        assert image.caption_ar_display == "Main menu"
        image.caption_ar = "القائمة"
        assert image.caption_ar_display == "القائمة"


class TestStaffAccountsOfARestaurant:
    """One restaurant can have the accounts it needs: one admin that does everything, or an
    admin and cashiers, or several of each."""

    @pytest.mark.parametrize(
        ("username", "role"),
        [
            ("gulf-food-admin", Role.ADMIN),
            ("gulf-food-admin2", Role.ADMIN),
            ("gulf-food-cashier", Role.CASHIER),
            ("gulf-food-cashier2", Role.CASHIER),
            ("gulf-food-cashier3", Role.CASHIER),
        ],
    )
    def test_the_naming_convention_is_a_valid_username(
        self, username: str, role: Role
    ) -> None:
        member = make_member(make_restaurant("gulf-food"), username, role)

        member.full_clean()

        assert len(username) <= 30

    def test_a_restaurant_can_have_several_admins_and_several_cashiers(self) -> None:
        restaurant = make_restaurant("gulf-food")
        make_member(restaurant, "gulf-food-admin", Role.ADMIN)
        make_member(restaurant, "gulf-food-admin2", Role.ADMIN)
        make_member(restaurant, "gulf-food-cashier", Role.CASHIER)
        make_member(restaurant, "gulf-food-cashier2", Role.CASHIER)

        roles = list(
            StaffMembership.objects.filter(restaurant=restaurant)
            .order_by("user__username")
            .values_list("role", flat=True)
        )

        assert roles == ["admin", "admin", "cashier", "cashier"]

    def test_a_small_restaurant_can_work_with_one_admin_account_only(self) -> None:
        restaurant = make_restaurant("gulf-food")
        admin = make_member(restaurant, "gulf-food-admin", Role.ADMIN)

        # The one admin sees and decides orders (what a cashier does) and manages the rest.
        assert role_has_permission(admin.role, Permission.ORDERS_VIEW)
        assert role_has_permission(admin.role, Permission.ORDERS_DECIDE)
        assert role_has_permission(admin.role, Permission.MENU_EDIT)
