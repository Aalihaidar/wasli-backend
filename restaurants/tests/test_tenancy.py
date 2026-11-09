"""One restaurant can never read or change another's data, and a role only does what its
permission codes allow."""

import pytest
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from core.permissions import Permission, Role
from restaurants.models import RestaurantMenuImage, StaffMembership
from restaurants.permissions import get_membership, require_permission
from restaurants.services import resolve_membership
from restaurants.tests.factories import make_member, make_restaurant, make_user
from users.models import User

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


class OrdersView(APIView):  # type: ignore[misc]
    permission_classes = [require_permission(Permission.ORDERS_VIEW)]  # noqa: RUF012

    def get(self, request: Request, restaurant_slug: str | None = None) -> Response:
        membership = get_membership(request)
        return Response({"restaurant": membership.restaurant.slug})


class MenuEditView(APIView):  # type: ignore[misc]
    permission_classes = [require_permission(Permission.MENU_EDIT)]  # noqa: RUF012

    def get(self, request: Request, restaurant_slug: str | None = None) -> Response:
        return Response({"restaurant": get_membership(request).restaurant.slug})


def call(view: type[APIView], user: User | None, **kwargs: str) -> Response:
    request = factory.get("/x/")
    if user is not None:
        force_authenticate(request, user=user)
    return view.as_view()(request, **kwargs)


class TestScopedQueryset:
    def test_a_restaurant_only_sees_its_own_rows(self) -> None:
        a, b = make_restaurant("cafe-a"), make_restaurant("cafe-b")
        image_a = RestaurantMenuImage.objects.create(restaurant=a, image="a.jpg")
        RestaurantMenuImage.objects.create(restaurant=b, image="b.jpg")

        assert list(RestaurantMenuImage.objects.for_restaurant(a)) == [image_a]

    def test_it_accepts_the_restaurant_or_its_id(self) -> None:
        a = make_restaurant("cafe-a")
        image = RestaurantMenuImage.objects.create(restaurant=a, image="a.jpg")

        assert list(RestaurantMenuImage.objects.for_restaurant(a.pk)) == [image]
        assert list(RestaurantMenuImage.objects.for_restaurant(str(a.pk))) == [image]

    def test_it_chains_with_other_filters(self) -> None:
        a = make_restaurant("cafe-a")
        RestaurantMenuImage.objects.create(restaurant=a, image="a.jpg", sort_order=2)
        wanted = RestaurantMenuImage.objects.create(
            restaurant=a, image="a2.jpg", sort_order=1
        )

        found = RestaurantMenuImage.objects.for_restaurant(a).filter(sort_order=1)

        assert list(found) == [wanted]

    def test_membership_rows_are_scoped_too(self) -> None:
        a, b = make_restaurant("cafe-a"), make_restaurant("cafe-b")
        member_a = make_member(a, "sara")
        make_member(b, "omar")

        assert list(StaffMembership.objects.for_restaurant(a)) == [member_a]


class TestPermissionClass:
    def test_a_cashier_may_view_orders(self) -> None:
        member = make_member(make_restaurant("cafe-a"), "sara", Role.CASHIER)

        response = call(OrdersView, member.user)

        assert response.status_code == 200
        assert response.data == {"restaurant": "cafe-a"}

    def test_a_cashier_may_not_edit_the_menu(self) -> None:
        member = make_member(make_restaurant("cafe-a"), "sara", Role.CASHIER)

        assert call(MenuEditView, member.user).status_code == 403

    def test_an_admin_may_edit_the_menu(self) -> None:
        member = make_member(make_restaurant("cafe-a"), "boss", Role.ADMIN)

        assert call(MenuEditView, member.user).status_code == 200

    def test_nobody_signed_in_is_refused(self) -> None:
        make_restaurant("cafe-a")

        assert call(OrdersView, None).status_code in {401, 403}

    def test_a_user_without_a_membership_is_refused(self) -> None:
        make_restaurant("cafe-a")

        assert call(OrdersView, make_user("customer")).status_code == 403

    def test_staff_of_restaurant_a_cannot_act_on_restaurant_b(self) -> None:
        make_member(make_restaurant("cafe-a"), "sara", Role.ADMIN)
        outsider = make_member(make_restaurant("cafe-b"), "omar", Role.ADMIN)
        # Omar is an admin, but only of cafe-b.
        assert (
            call(OrdersView, outsider.user, restaurant_slug="cafe-a").status_code == 403
        )
        assert (
            call(OrdersView, outsider.user, restaurant_slug="cafe-b").status_code == 200
        )

    def test_a_deactivated_member_is_refused(self) -> None:
        restaurant = make_restaurant("cafe-a")
        make_member(restaurant, "boss", Role.ADMIN)
        member = make_member(restaurant, "sara", Role.CASHIER, is_active=False)

        assert call(OrdersView, member.user).status_code == 403

    def test_a_deactivated_restaurant_locks_its_staff_out(self) -> None:
        restaurant = make_restaurant("cafe-a", is_active=False)
        member = make_member(restaurant, "sara", Role.CASHIER)

        assert call(OrdersView, member.user).status_code == 403

    def test_several_memberships_need_a_restaurant_slug(self) -> None:
        a, b = make_restaurant("cafe-a"), make_restaurant("cafe-b")
        member = make_member(a, "sara", Role.CASHIER)
        StaffMembership.objects.create(restaurant=b, user=member.user, role="cashier")

        assert call(OrdersView, member.user).status_code == 403
        chosen = call(OrdersView, member.user, restaurant_slug="cafe-b")
        assert chosen.status_code == 200
        assert chosen.data == {"restaurant": "cafe-b"}

    def test_the_role_can_differ_between_restaurants(self) -> None:
        a, b = make_restaurant("cafe-a"), make_restaurant("cafe-b")
        member = make_member(a, "sara", Role.ADMIN)
        StaffMembership.objects.create(restaurant=b, user=member.user, role="cashier")

        edit_a = call(MenuEditView, member.user, restaurant_slug="cafe-a")
        edit_b = call(MenuEditView, member.user, restaurant_slug="cafe-b")

        assert edit_a.status_code == 200
        assert edit_b.status_code == 403

    def test_a_platform_superuser_is_not_a_restaurant_member(self) -> None:
        make_restaurant("cafe-a")
        superuser = User.objects.create_superuser(
            "owner", "pw-for-tests-1", email="owner@example.com"
        )

        # The Django admin is how the platform team works; the staff API needs a membership.
        assert call(OrdersView, superuser).status_code == 403


class TestResolveMembership:
    def test_no_membership_gives_none(self) -> None:
        assert resolve_membership(make_user("nobody")) is None

    def test_the_single_membership_is_returned(self) -> None:
        member = make_member(make_restaurant("cafe-a"), "sara")

        assert resolve_membership(member.user) == member
        assert resolve_membership(member.user, "cafe-a") == member
        assert resolve_membership(member.user, "cafe-b") is None
