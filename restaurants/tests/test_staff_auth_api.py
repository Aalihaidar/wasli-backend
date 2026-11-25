"""The staff sign-in, sign-out, password change and ``GET /staff/me``, the way the restaurant
app calls them."""

from typing import Any

import pytest
from django.contrib.auth import authenticate
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from core.permissions import Permission, Role
from customers.tests.factories import make_customer
from restaurants.models import StaffMembership
from restaurants.tests.factories import (
    PASSWORD,
    make_member,
    make_restaurant,
)
from users.models import User

pytestmark = pytest.mark.django_db

BASE = "/api/v1"
LOGIN = f"{BASE}/auth/login"
LOGOUT = f"{BASE}/auth/logout"
CHANGE_PASSWORD = f"{BASE}/auth/password"
ME = f"{BASE}/staff/me"

NEW_PASSWORD = "another-long-passphrase-2"


@pytest.fixture(autouse=True)
def _generous_throttles(monkeypatch: pytest.MonkeyPatch) -> None:
    """The scoped limits are for production; a test that signs in many times would meet them."""
    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {"staff_login": "10000/min", "staff_password": "10000/min"},
    )


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Token {token}"}


def sign_in(
    api: APIClient, username: str = "cafe-cashier", password: str = PASSWORD
) -> Any:
    return api.post(LOGIN, {"username": username, "password": password}, format="json")


def token_of(api: APIClient, username: str = "cafe-cashier") -> str:
    response = sign_in(api, username)
    assert response.status_code == 200, response.content
    return str(response.json()["token"])


def first_error(response: Any) -> dict[str, Any]:
    return dict(response.json()["errors"][0])


def a_member(
    slug: str = "cafe-one",
    username: str = "cafe-cashier",
    role: Role = Role.CASHIER,
    **restaurant: object,
) -> StaffMembership:
    return make_member(make_restaurant(slug, **restaurant), username, role)


class TestLogin:
    def test_a_member_gets_a_token(self, api: APIClient) -> None:
        member = a_member()

        response = sign_in(api)

        assert response.status_code == 200
        assert response.json() == {"token": Token.objects.get(user=member.user).key}

    def test_every_sign_in_of_an_account_returns_the_same_token(
        self, api: APIClient
    ) -> None:
        a_member()

        first, second = token_of(api), token_of(api)

        assert first == second
        assert Token.objects.count() == 1

    def test_the_username_is_not_case_sensitive(self, api: APIClient) -> None:
        a_member()

        assert sign_in(api, "Cafe-Cashier").status_code == 200

    def test_an_email_or_a_phone_number_also_works(self, api: APIClient) -> None:
        member = a_member()
        member.user.email = "member@example.com"
        member.user.phone = "+971500000042"
        member.user.save()

        assert sign_in(api, "Member@Example.com").status_code == 200
        assert sign_in(api, "050 000 0042").status_code == 200

    def test_the_sign_in_is_recorded(self, api: APIClient) -> None:
        member = a_member()
        assert member.user.last_login is None

        sign_in(api)

        member.user.refresh_from_db()
        assert member.user.last_login is not None

    def test_a_stale_token_in_the_header_is_never_read(self, api: APIClient) -> None:
        a_member()

        response = api.post(
            LOGIN,
            {"username": "cafe-cashier", "password": PASSWORD},
            format="json",
            headers=headers("not-a-real-token"),
        )

        assert response.status_code == 200

    def test_an_unreadable_body_is_a_validation_error(self, api: APIClient) -> None:
        response = api.post(LOGIN, {"username": "cafe-cashier"}, format="json")

        assert response.status_code == 400
        assert first_error(response)["attr"] == "password"
        assert first_error(response)["code"] == "required"


class TestLoginRefusals:
    """Every refusal is the same answer and creates no token, so the endpoint never says
    which accounts exist or why one was refused."""

    def refused(self, api: APIClient, username: str, password: str = PASSWORD) -> Any:
        response = sign_in(api, username, password)
        assert response.status_code == 401, response.content
        assert first_error(response)["code"] == "authentication_failed"
        assert Token.objects.count() == 0
        return response.json()

    def test_a_wrong_password_and_an_unknown_account_look_the_same(
        self, api: APIClient
    ) -> None:
        a_member()

        wrong_password = self.refused(api, "cafe-cashier", "not-the-password")
        unknown = self.refused(api, "nobody-here")

        assert wrong_password == unknown

    def test_an_inactive_account_is_refused(self, api: APIClient) -> None:
        member = a_member()
        member.user.is_active = False
        member.user.save()

        self.refused(api, "cafe-cashier")

    def test_a_deactivated_member_is_refused(self, api: APIClient) -> None:
        a_member()
        StaffMembership.objects.update(is_active=False)

        self.refused(api, "cafe-cashier")

    def test_a_member_of_a_deactivated_restaurant_is_refused(
        self, api: APIClient
    ) -> None:
        a_member(is_active=False)

        self.refused(api, "cafe-cashier")

    def test_the_platform_team_without_a_membership_is_refused(
        self, api: APIClient
    ) -> None:
        User.objects.create_superuser(
            "platform-owner", PASSWORD, email="owner@example.com"
        )

        self.refused(api, "platform-owner")
        self.refused(api, "owner@example.com")

    def test_a_customer_is_refused(self, api: APIClient) -> None:
        make_customer("sara@example.com")

        self.refused(api, "sara@example.com")

    def test_an_account_of_two_restaurants_is_refused_for_now(
        self, api: APIClient
    ) -> None:
        """One restaurant per account in the first version: with two memberships the call
        would not know which restaurant is meant (``resolve_membership``)."""
        member = a_member("cafe-one")
        StaffMembership.objects.create(
            restaurant=make_restaurant("cafe-two"),
            user=member.user,
            role=Role.CASHIER.value,
        )

        self.refused(api, "cafe-cashier")


class TestLoginLimits:
    def test_ten_wrong_tries_for_a_username_block_even_the_right_password(
        self, api: APIClient
    ) -> None:
        a_member()
        for _ in range(10):
            assert sign_in(api, password="wrong-password-1").status_code == 401

        blocked = sign_in(api)

        assert blocked.status_code == 429
        assert first_error(blocked)["code"] == "throttled"
        assert Token.objects.count() == 0

    def test_the_count_does_not_depend_on_how_the_username_is_written(
        self, api: APIClient
    ) -> None:
        a_member()
        for _ in range(10):
            sign_in(api, " CAFE-cashier ", "wrong-password-1")

        assert sign_in(api).status_code == 429

    def test_a_good_sign_in_clears_the_count(self, api: APIClient) -> None:
        a_member()
        for _ in range(9):
            sign_in(api, password="wrong-password-1")
        assert sign_in(api).status_code == 200

        statuses = [
            sign_in(api, password="wrong-password-1").status_code for _ in range(9)
        ]

        assert statuses == [401] * 9

    def test_one_username_does_not_block_another(self, api: APIClient) -> None:
        a_member()
        make_member(make_restaurant("cafe-two"), "other-cashier")
        for _ in range(11):
            sign_in(api, password="wrong-password-1")

        assert sign_in(api, "other-cashier").status_code == 200

    def test_the_address_has_its_own_throttle(
        self, api: APIClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ScopedRateThrottle, "THROTTLE_RATES", {"staff_login": "2/min"}
        )

        statuses = [sign_in(api, f"nobody-{n}").status_code for n in range(3)]

        assert statuses == [401, 401, 429]

    def test_the_real_rates_are_set_for_every_staff_scope(self) -> None:
        from django.conf import settings

        rates: dict[str, str] = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]  # type: ignore[assignment]
        assert rates["staff_login"] == "10/min"
        assert rates["staff_password"] == "10/hour"


class TestLogout:
    def test_the_token_is_deleted_and_stops_working(self, api: APIClient) -> None:
        a_member()
        token = token_of(api)

        response = api.post(LOGOUT, headers=headers(token))

        assert response.status_code == 204
        assert not Token.objects.exists()
        assert api.get(ME, headers=headers(token)).status_code == 401

    def test_a_new_sign_in_after_a_sign_out_gives_a_new_token(
        self, api: APIClient
    ) -> None:
        a_member()
        first = token_of(api)
        api.post(LOGOUT, headers=headers(first))

        assert token_of(api) != first

    def test_a_member_who_lost_the_membership_can_still_sign_out(
        self, api: APIClient
    ) -> None:
        a_member()
        token = token_of(api)
        StaffMembership.objects.update(is_active=False)

        assert api.post(LOGOUT, headers=headers(token)).status_code == 204

    def test_it_needs_a_token(self, api: APIClient) -> None:
        response = api.post(LOGOUT)

        assert response.status_code == 401
        assert first_error(response)["code"] == "not_authenticated"

    def test_a_customer_token_does_not_sign_out_a_member(self, api: APIClient) -> None:
        response = api.post(LOGOUT, headers={"Authorization": "Customer abc"})

        assert response.status_code == 401
        assert first_error(response)["code"] == "not_authenticated"


class TestMe:
    def test_a_cashier_reads_their_profile(self, api: APIClient) -> None:
        member = a_member(
            latitude=25.2001, longitude=55.2701, service_radius_m=300, name_ar="مقهى"
        )
        token = token_of(api)

        response = api.get(ME, headers=headers(token))

        assert response.status_code == 200
        assert response.json() == {
            "id": str(member.user.pk),
            "username": "cafe-cashier",
            "full_name": "",
            "role": "cashier",
            "permissions": ["orders.decide", "orders.view"],
            "must_change_password": False,
            "restaurant": {
                "slug": "cafe-one",
                "name_en": "Cafe One",
                "name_ar": "مقهى",
                "logo_url": None,
                "latitude": 25.2001,
                "longitude": 55.2701,
                "service_radius_m": 300,
                "currency": "AED",
            },
        }

    def test_an_admin_has_every_permission(self, api: APIClient) -> None:
        a_member(username="cafe-admin", role=Role.ADMIN)
        token = token_of(api, "cafe-admin")

        body = api.get(ME, headers=headers(token)).json()

        assert body["role"] == "admin"
        assert body["permissions"] == sorted(p.value for p in Permission)

    def test_the_service_distance_is_absent_when_the_restaurant_has_none(
        self, api: APIClient
    ) -> None:
        a_member()
        token = token_of(api)

        restaurant = api.get(ME, headers=headers(token)).json()["restaurant"]

        assert "service_radius_m" not in restaurant

    def test_the_logo_is_an_absolute_url(self, api: APIClient) -> None:
        a_member(logo="restaurants/cafe-one/logo/logo.png")
        token = token_of(api)

        logo = api.get(ME, headers=headers(token)).json()["restaurant"]["logo_url"]

        assert logo.startswith("http")
        assert logo.endswith("restaurants/cafe-one/logo/logo.png")

    def test_an_english_only_restaurant_has_the_english_name_in_arabic_too(
        self, api: APIClient
    ) -> None:
        a_member(name_ar="")
        token = token_of(api)

        restaurant = api.get(ME, headers=headers(token)).json()["restaurant"]

        assert restaurant["name_ar"] == restaurant["name_en"] == "Cafe One"

    def test_the_flag_for_a_temporary_password_is_shown_and_blocks_nothing(
        self, api: APIClient
    ) -> None:
        member = a_member()
        member.user.must_change_password = True
        member.user.save()
        token = token_of(api)

        response = api.get(ME, headers=headers(token))

        assert response.status_code == 200
        assert response.json()["must_change_password"] is True

    def test_each_member_sees_only_their_own_restaurant(self, api: APIClient) -> None:
        a_member("cafe-a", "a-cashier")
        a_member("cafe-b", "b-cashier")

        slug_a = api.get(ME, headers=headers(token_of(api, "a-cashier"))).json()
        slug_b = api.get(ME, headers=headers(token_of(api, "b-cashier"))).json()

        assert slug_a["restaurant"]["slug"] == "cafe-a"
        assert slug_b["restaurant"]["slug"] == "cafe-b"

    def test_it_needs_a_token(self, api: APIClient) -> None:
        response = api.get(ME)

        assert response.status_code == 401
        assert first_error(response)["code"] == "not_authenticated"

    def test_an_unknown_token_is_refused(self, api: APIClient) -> None:
        response = api.get(ME, headers=headers("not-a-real-token"))

        assert response.status_code == 401
        assert first_error(response)["code"] == "authentication_failed"

    def test_an_inactive_account_with_a_token_is_refused(self, api: APIClient) -> None:
        member = a_member()
        token = token_of(api)
        member.user.is_active = False
        member.user.save()

        assert api.get(ME, headers=headers(token)).status_code == 401

    @pytest.mark.parametrize("what", ["member", "restaurant", "two restaurants"])
    def test_an_account_that_is_no_longer_a_member_is_forbidden(
        self, api: APIClient, what: str
    ) -> None:
        member = a_member()
        token = token_of(api)
        if what == "member":
            StaffMembership.objects.update(is_active=False)
        elif what == "restaurant":
            member.restaurant.is_active = False
            member.restaurant.save()
        else:
            StaffMembership.objects.create(
                restaurant=make_restaurant("cafe-two"),
                user=member.user,
                role=Role.CASHIER.value,
            )

        response = api.get(ME, headers=headers(token))

        assert response.status_code == 403
        assert first_error(response)["code"] == "permission_denied"

    def test_a_customer_token_does_not_open_it(self, api: APIClient) -> None:
        response = api.get(ME, headers={"Authorization": "Customer abc"})

        assert response.status_code == 401


class TestChangePassword:
    def body(self, current: str = PASSWORD, new: str = NEW_PASSWORD) -> dict[str, str]:
        return {"current_password": current, "new_password": new}

    def test_the_password_changes_and_the_token_stays_valid(
        self, api: APIClient
    ) -> None:
        member = a_member()
        member.user.must_change_password = True
        member.user.save()
        token = token_of(api)

        response = api.post(
            CHANGE_PASSWORD, self.body(), format="json", headers=headers(token)
        )

        assert response.status_code == 204
        assert response.content == b""
        member.user.refresh_from_db()
        assert member.user.must_change_password is False
        assert authenticate(username="cafe-cashier", password=NEW_PASSWORD) is not None
        assert authenticate(username="cafe-cashier", password=PASSWORD) is None
        me = api.get(ME, headers=headers(token))
        assert me.status_code == 200
        assert me.json()["must_change_password"] is False
        assert sign_in(api, password=NEW_PASSWORD).json() == {"token": token}

    def test_a_wrong_current_password_changes_nothing(self, api: APIClient) -> None:
        member = a_member()
        token = token_of(api)

        response = api.post(
            CHANGE_PASSWORD,
            self.body(current="not-the-password"),
            format="json",
            headers=headers(token),
        )

        assert response.status_code == 400
        error = first_error(response)
        assert (error["code"], error["attr"]) == (
            "password_incorrect",
            "current_password",
        )
        member.user.refresh_from_db()
        assert member.user.check_password(PASSWORD)

    def test_the_new_password_must_differ(self, api: APIClient) -> None:
        a_member()
        token = token_of(api)

        response = api.post(
            CHANGE_PASSWORD,
            self.body(new=PASSWORD),
            format="json",
            headers=headers(token),
        )

        assert response.status_code == 400
        error = first_error(response)
        assert (error["code"], error["attr"]) == ("password_unchanged", "new_password")

    @pytest.mark.parametrize(
        ("new_password", "code"),
        [
            ("short-1", "password_too_short"),
            ("9482716350", "password_entirely_numeric"),
            ("password1234", "password_too_common"),
        ],
    )
    def test_a_weak_new_password_is_refused_with_the_rule_that_failed(
        self, api: APIClient, new_password: str, code: str
    ) -> None:
        member = a_member()
        token = token_of(api)

        response = api.post(
            CHANGE_PASSWORD,
            self.body(new=new_password),
            format="json",
            headers=headers(token),
        )

        assert response.status_code == 400
        errors = response.json()["errors"]
        assert code in [error["code"] for error in errors]
        assert {error["attr"] for error in errors} == {"new_password"}
        member.user.refresh_from_db()
        assert member.user.check_password(PASSWORD)

    def test_both_fields_are_required(self, api: APIClient) -> None:
        a_member()
        token = token_of(api)

        response = api.post(CHANGE_PASSWORD, {}, format="json", headers=headers(token))

        assert response.status_code == 400
        assert {e["attr"] for e in response.json()["errors"]} == {
            "current_password",
            "new_password",
        }

    def test_it_needs_a_token(self, api: APIClient) -> None:
        response = api.post(CHANGE_PASSWORD, self.body(), format="json")

        assert response.status_code == 401

    def test_an_account_that_is_no_longer_a_member_is_forbidden(
        self, api: APIClient
    ) -> None:
        a_member()
        token = token_of(api)
        StaffMembership.objects.update(is_active=False)

        response = api.post(
            CHANGE_PASSWORD, self.body(), format="json", headers=headers(token)
        )

        assert response.status_code == 403

    def test_it_is_throttled_per_account(
        self, api: APIClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a_member()
        token = token_of(api)
        monkeypatch.setattr(
            ScopedRateThrottle, "THROTTLE_RATES", {"staff_password": "2/min"}
        )

        statuses = [
            api.post(
                CHANGE_PASSWORD,
                self.body(current="not-the-password"),
                format="json",
                headers=headers(token),
            ).status_code
            for _ in range(3)
        ]

        assert statuses == [400, 400, 429]
