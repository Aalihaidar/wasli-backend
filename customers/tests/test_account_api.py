"""The customer-account endpoints, the way the customer site calls them."""

import logging
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from customers.models import Customer, CustomerSession, VerificationCode
from customers.tests.helpers import (
    CONTACT,
    CONTACT_VERIFY,
    EMAIL,
    LOGIN,
    LOGOUT,
    ME,
    NEW_PASSWORD,
    PASSWORD,
    PHONE,
    RESEND,
    RESET,
    RESET_CONFIRM,
    SIGNUP,
    VERIFY,
    customer_headers,
    generous_throttles,
    last_code,
    sent_messages,
    sign_up,
    verified_customer,
)
from messaging.models import OutboxMessage
from users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _outbox_and_room(settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    settings.MESSAGING_BACKEND = "outbox"
    settings.ENVIRONMENT = "local"
    generous_throttles(monkeypatch)


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def first_error(response: Any) -> dict[str, Any]:
    return dict(response.json()["errors"][0])


def codes(response: Any) -> list[str]:
    return [error["code"] for error in response.json()["errors"]]


def age_codes(seconds: int) -> None:
    """Make every code older, so the 60-second wait has passed."""
    VerificationCode.objects.update(
        created_at=timezone.now() - timedelta(seconds=seconds)
    )


# --- sign up -------------------------------------------------------------------------------


class TestSignup:
    def test_an_email_sign_up_creates_an_unverified_account_and_sends_a_code(
        self, api: APIClient
    ) -> None:
        response = sign_up(api)

        assert response.status_code == 201
        assert response.json() == {
            "identifier": EMAIL,
            "channel": "email",
            "code_expires_in_seconds": 600,
            "resend_available_in_seconds": 60,
        }
        user = User.objects.get(email=EMAIL)
        assert user.email_verified_at is None and user.username is None
        assert user.check_password(PASSWORD)
        customer = Customer.objects.get(user=user)
        assert (customer.display_name, customer.locale) == ("Sara Example", "en")
        [message] = sent_messages(EMAIL)
        assert message.channel == "email" and "Wasli" in message.body

    def test_a_phone_sign_up_sends_an_sms_to_the_normalised_number(
        self, api: APIClient
    ) -> None:
        response = sign_up(api, email=None, phone="050 000 0001", locale="ar")

        assert response.status_code == 201
        assert response.json()["identifier"] == PHONE
        assert response.json()["channel"] == "sms"
        [message] = sent_messages(PHONE)
        assert message.channel == "sms" and message.subject == ""
        assert any("؀" <= ch <= "ۿ" for ch in message.body)  # the customer's language
        assert User.objects.get(phone=PHONE).phone_verified_at is None

    def test_the_email_is_stored_in_lower_case(self, api: APIClient) -> None:
        sign_up(api, email="Sara.Example@Example.COM")

        assert User.objects.filter(email=EMAIL).exists()

    def test_the_password_is_stored_hashed(self, api: APIClient) -> None:
        sign_up(api)

        assert PASSWORD not in User.objects.get(email=EMAIL).password

    @pytest.mark.parametrize(
        ("change", "code", "attr"),
        [
            ({"full_name": None}, "required", "full_name"),
            ({"password": None}, "required", "password"),
            ({"locale": None}, "required", "locale"),
            ({"locale": "fr"}, "invalid_choice", "locale"),
            ({"email": "not-an-email"}, "invalid", "email"),
            ({"password": "short1"}, "password_too_short", "password"),
            ({"password": "password1234"}, "password_too_common", "password"),
            ({"password": "9182736450123"}, "password_entirely_numeric", "password"),
            ({"email": None, "phone": "12"}, "invalid", "phone"),
        ],
    )
    def test_bad_input_is_a_400_with_a_stable_code(
        self, api: APIClient, change: dict[str, Any], code: str, attr: str
    ) -> None:
        response = sign_up(api, **change)

        assert response.status_code == 400
        assert response.json()["type"] == "validation_error"
        assert any(
            e["code"] == code and e["attr"] == attr for e in response.json()["errors"]
        )
        assert not User.objects.exists() and not OutboxMessage.objects.exists()

    def test_a_password_like_the_email_is_refused(self, api: APIClient) -> None:
        response = sign_up(
            api, email="sara.example@example.com", password="sara.example"
        )

        assert response.status_code == 400
        assert "password_too_similar" in codes(response)

    @pytest.mark.parametrize("both", [{}, {"phone": PHONE}])
    def test_neither_or_both_contacts_is_contact_required(
        self, api: APIClient, both: dict[str, Any]
    ) -> None:
        change: dict[str, Any] = {"email": None} if not both else {}
        response = sign_up(api, **change, **both)

        assert response.status_code == 400
        assert "contact_required" in codes(response)

    def test_a_verified_contact_is_account_exists(self, api: APIClient) -> None:
        verified_customer(api)

        response = sign_up(api, full_name="Someone Else", password=NEW_PASSWORD)

        assert response.status_code == 409
        assert first_error(response)["code"] == "account_exists"
        assert User.objects.get(email=EMAIL).check_password(PASSWORD)  # untouched

    def test_signing_up_again_before_verifying_restarts_the_sign_up(
        self, api: APIClient
    ) -> None:
        sign_up(api)
        age_codes(120)

        response = sign_up(
            api, full_name="Sara Restarted", password=NEW_PASSWORD, locale="ar"
        )

        assert response.status_code == 201
        user = User.objects.get(email=EMAIL)
        assert user.check_password(NEW_PASSWORD) and not user.check_password(PASSWORD)
        customer = Customer.objects.get(user=user)
        assert (customer.display_name, customer.locale) == ("Sara Restarted", "ar")
        assert User.objects.count() == 1
        assert len(sent_messages(EMAIL)) == 2
        open_codes = VerificationCode.objects.filter(
            consumed_at=None, invalidated_at=None
        )
        assert open_codes.count() == 1  # the first code was replaced

    def test_a_restart_inside_the_wait_changes_nothing(self, api: APIClient) -> None:
        sign_up(api)

        response = sign_up(api, password=NEW_PASSWORD)

        assert response.status_code == 429
        assert User.objects.get(email=EMAIL).check_password(PASSWORD)  # rolled back

    def test_a_staff_account_with_that_email_is_account_exists(
        self, api: APIClient
    ) -> None:
        User.objects.create_user("boss", "pw-for-tests-123", email=EMAIL)

        response = sign_up(api)

        assert response.status_code == 409
        assert not Customer.objects.exists()

    def test_the_platform_team_email_is_account_exists(self, api: APIClient) -> None:
        User.objects.create_superuser("owner", "pw-for-tests-123", email=EMAIL)

        assert sign_up(api).status_code == 409

    def test_nothing_is_created_when_the_message_cannot_be_sent(
        self, api: APIClient, settings: Any
    ) -> None:
        settings.MESSAGING_BACKEND = "disabled"

        with pytest.raises(Exception, match="disabled"):
            sign_up(api)

        assert not User.objects.exists() and not Customer.objects.exists()

    def test_the_answer_is_not_cached_and_needs_no_token(self, api: APIClient) -> None:
        response = sign_up(api, **{})

        assert response["Cache-Control"] == "no-store"
        assert (
            api.post(
                SIGNUP, {}, format="json", headers={"Authorization": "Token junk"}
            ).status_code
            == 400
        )


# --- verify --------------------------------------------------------------------------------


class TestVerify:
    def test_the_right_code_verifies_and_returns_the_token_and_the_profile(
        self, api: APIClient
    ) -> None:
        sign_up(api)

        response = api.post(
            VERIFY, {"identifier": EMAIL, "code": last_code(EMAIL)}, format="json"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["customer"] == {
            "id": str(Customer.objects.get().pk),
            "full_name": "Sara Example",
            "locale": "en",
            "email": EMAIL,
            "email_verified": True,
            "phone": None,
            "phone_verified": False,
        }
        assert len(body["token"]) >= 40
        assert User.objects.get(email=EMAIL).email_verified_at is not None

    def test_the_token_is_stored_only_as_a_hash_and_opens_the_profile(
        self, api: APIClient
    ) -> None:
        token, _ = verified_customer(api)

        session = CustomerSession.objects.get()
        assert token not in session.token_hash
        assert api.get(ME, headers=customer_headers(token)).status_code == 200

    def test_a_phone_is_verified_by_its_own_code(self, api: APIClient) -> None:
        sign_up(api, email=None, phone=PHONE)

        response = api.post(
            VERIFY,
            {"identifier": "050 000 0001", "code": last_code(PHONE)},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["customer"]["phone_verified"] is True
        assert response.json()["customer"]["email_verified"] is False

    def test_a_wrong_code_is_code_invalid(self, api: APIClient) -> None:
        sign_up(api)
        good = last_code(EMAIL)
        wrong = "000000" if good != "000000" else "111111"

        response = api.post(VERIFY, {"identifier": EMAIL, "code": wrong}, format="json")

        assert response.status_code == 400
        assert first_error(response)["code"] == "code_invalid"
        assert User.objects.get(email=EMAIL).email_verified_at is None

    def test_five_wrong_codes_then_too_many_attempts_even_for_the_right_one(
        self, api: APIClient
    ) -> None:
        sign_up(api)
        good = last_code(EMAIL)
        wrong = "000000" if good != "000000" else "111111"
        for _ in range(5):
            assert (
                api.post(
                    VERIFY, {"identifier": EMAIL, "code": wrong}, format="json"
                ).status_code
                == 400
            )

        response = api.post(VERIFY, {"identifier": EMAIL, "code": good}, format="json")

        assert response.status_code == 429
        assert first_error(response)["code"] == "too_many_attempts"

    def test_a_new_code_after_too_many_attempts_works(self, api: APIClient) -> None:
        sign_up(api)
        wrong = "000000" if last_code(EMAIL) != "000000" else "111111"
        for _ in range(5):
            api.post(VERIFY, {"identifier": EMAIL, "code": wrong}, format="json")
        age_codes(120)
        api.post(RESEND, {"identifier": EMAIL}, format="json")

        response = api.post(
            VERIFY, {"identifier": EMAIL, "code": last_code(EMAIL)}, format="json"
        )

        assert response.status_code == 200

    def test_an_expired_code_is_code_expired(self, api: APIClient) -> None:
        sign_up(api)
        VerificationCode.objects.update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        response = api.post(
            VERIFY, {"identifier": EMAIL, "code": last_code(EMAIL)}, format="json"
        )

        assert response.status_code == 400
        assert first_error(response)["code"] == "code_expired"

    def test_a_code_works_only_once(self, api: APIClient) -> None:
        sign_up(api)
        code = last_code(EMAIL)
        api.post(VERIFY, {"identifier": EMAIL, "code": code}, format="json")

        again = api.post(VERIFY, {"identifier": EMAIL, "code": code}, format="json")

        assert again.status_code == 400 and first_error(again)["code"] == "code_invalid"

    def test_an_unknown_contact_gets_code_invalid_so_nothing_is_revealed(
        self, api: APIClient
    ) -> None:
        response = api.post(
            VERIFY,
            {"identifier": "nobody@example.com", "code": "123456"},
            format="json",
        )

        assert response.status_code == 400
        assert first_error(response)["code"] == "code_invalid"

    def test_another_accounts_code_never_works(self, api: APIClient) -> None:
        sign_up(api)
        other_code = last_code(EMAIL)
        sign_up(api, email="omar.example@example.com")

        response = api.post(
            VERIFY,
            {"identifier": "omar.example@example.com", "code": other_code},
            format="json",
        )

        # Only a coincidence of two random codes could pass; the two are different here.
        if other_code != last_code("omar.example@example.com"):
            assert response.status_code == 400
        assert User.objects.get(email=EMAIL).email_verified_at is None

    @pytest.mark.parametrize("code", ["12345", "1234567", "abcdef", "12 456", ""])
    def test_a_malformed_code_is_a_validation_error_and_costs_no_attempt(
        self, api: APIClient, code: str
    ) -> None:
        sign_up(api)

        response = api.post(VERIFY, {"identifier": EMAIL, "code": code}, format="json")

        assert response.status_code == 400
        assert response.json()["type"] == "validation_error"
        assert VerificationCode.objects.get().attempts == 0

    def test_a_blocked_customer_is_refused(self, api: APIClient) -> None:
        sign_up(api)
        Customer.objects.update(is_blocked=True)

        response = api.post(
            VERIFY, {"identifier": EMAIL, "code": last_code(EMAIL)}, format="json"
        )

        assert response.status_code == 403
        assert not CustomerSession.objects.exists()

    def test_a_username_is_not_a_contact(self, api: APIClient) -> None:
        response = api.post(
            VERIFY, {"identifier": "sara_example", "code": "123456"}, format="json"
        )

        assert response.status_code == 400
        assert response.json()["type"] == "validation_error"


# --- resend --------------------------------------------------------------------------------


class TestResend:
    def test_an_unverified_account_gets_a_new_code_and_the_old_one_stops_working(
        self, api: APIClient
    ) -> None:
        sign_up(api)
        old = last_code(EMAIL)
        age_codes(120)

        response = api.post(RESEND, {"identifier": EMAIL}, format="json")

        assert response.status_code == 202
        assert response.json()["resend_available_in_seconds"] == 60
        assert len(sent_messages(EMAIL)) == 2
        new = last_code(EMAIL)
        if old != new:
            assert (
                api.post(
                    VERIFY, {"identifier": EMAIL, "code": old}, format="json"
                ).status_code
                == 400
            )
        assert (
            api.post(
                VERIFY, {"identifier": EMAIL, "code": new}, format="json"
            ).status_code
            == 200
        )

    def test_inside_the_wait_it_is_throttled_with_retry_after(
        self, api: APIClient
    ) -> None:
        sign_up(api)

        response = api.post(RESEND, {"identifier": EMAIL}, format="json")

        assert response.status_code == 429
        assert first_error(response)["code"] == "throttled"
        assert 1 <= int(response["Retry-After"]) <= 60
        assert len(sent_messages(EMAIL)) == 1

    def test_five_an_hour_then_throttled(self, api: APIClient) -> None:
        sign_up(api)
        for _ in range(4):
            age_codes(120)
            assert (
                api.post(RESEND, {"identifier": EMAIL}, format="json").status_code
                == 202
            )
        # Five codes now sit inside the hour; make them recent enough to count and old enough to wait.
        VerificationCode.objects.update(
            created_at=timezone.now() - timedelta(minutes=5)
        )

        response = api.post(RESEND, {"identifier": EMAIL}, format="json")

        assert response.status_code == 429
        assert int(response["Retry-After"]) > 60

    def test_an_unknown_contact_gets_the_same_answer_and_nothing_is_sent(
        self, api: APIClient
    ) -> None:
        response = api.post(RESEND, {"identifier": "nobody@example.com"}, format="json")

        assert response.status_code == 202
        assert response.json()["identifier"] == "nobody@example.com"
        assert not OutboxMessage.objects.exists()

    def test_a_verified_account_gets_the_same_answer_and_nothing_is_sent(
        self, api: APIClient
    ) -> None:
        verified_customer(api)
        before = OutboxMessage.objects.count()

        response = api.post(RESEND, {"identifier": EMAIL}, format="json")

        assert response.status_code == 202
        assert OutboxMessage.objects.count() == before

    def test_an_invalid_contact_is_a_400(self, api: APIClient) -> None:
        response = api.post(RESEND, {"identifier": "12"}, format="json")

        assert response.status_code == 400


# --- sign in -------------------------------------------------------------------------------


class TestLogin:
    def test_a_verified_customer_signs_in_with_the_email(self, api: APIClient) -> None:
        verified_customer(api)

        response = api.post(
            LOGIN, {"identifier": EMAIL.upper(), "password": PASSWORD}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["customer"]["email"] == EMAIL
        assert CustomerSession.objects.count() == 2  # one at verification, one now

    def test_a_verified_customer_signs_in_with_the_phone(self, api: APIClient) -> None:
        sign_up(api, email=None, phone=PHONE)
        api.post(VERIFY, {"identifier": PHONE, "code": last_code(PHONE)}, format="json")

        response = api.post(
            LOGIN, {"identifier": "050 000 0001", "password": PASSWORD}, format="json"
        )

        assert response.status_code == 200

    @pytest.mark.parametrize(
        "identifier", ["nobody@example.com", "+971500000099", "sara_example", "", "   "]
    )
    def test_an_unknown_contact_is_a_401_like_a_wrong_password(
        self, api: APIClient, identifier: str
    ) -> None:
        response = api.post(
            LOGIN, {"identifier": identifier, "password": PASSWORD}, format="json"
        )

        assert response.status_code in {400, 401}
        if response.status_code == 401:
            assert first_error(response)["code"] == "authentication_failed"

    def test_a_wrong_password_is_a_401_with_no_challenge_header(
        self, api: APIClient
    ) -> None:
        verified_customer(api)

        response = api.post(
            LOGIN, {"identifier": EMAIL, "password": "wrong-password-1"}, format="json"
        )

        assert response.status_code == 401
        assert first_error(response)["code"] == "authentication_failed"
        assert "WWW-Authenticate" not in response

    def test_the_answer_is_the_same_for_a_wrong_password_and_an_unknown_contact(
        self, api: APIClient
    ) -> None:
        verified_customer(api)

        known = api.post(
            LOGIN, {"identifier": EMAIL, "password": "wrong-password-1"}, format="json"
        )
        unknown = api.post(
            LOGIN,
            {"identifier": "x@example.com", "password": "wrong-password-1"},
            format="json",
        )

        assert known.json() == unknown.json()

    @pytest.mark.parametrize("missing", ["identifier", "password"])
    def test_a_blank_field_is_a_400_that_names_it(
        self, api: APIClient, missing: str
    ) -> None:
        body = {"identifier": EMAIL, "password": PASSWORD, missing: ""}

        response = api.post(LOGIN, body, format="json")

        assert response.status_code == 400
        assert first_error(response)["attr"] == missing

    def test_the_contract_declares_the_refusals_of_a_sign_in(self) -> None:
        # drf-spectacular is only partly typed
        schema = SchemaGenerator().get_schema(request=None, public=True)  # type: ignore[no-untyped-call]
        responses = schema["paths"]["/api/v1/customers/login"]["post"]["responses"]

        examples = {
            code: responses[code]["content"]["application/json"]["examples"]
            for code in ("401", "403")
        }
        assert {"401", "403", "429"} <= set(responses)
        assert (
            examples["401"]["WrongPasswordOrUnknownContact"]["value"]["errors"][0][
                "code"
            ]
            == "authentication_failed"
        )
        assert {"AccountNotVerified", "BlockedOrDeactivated"} <= set(examples["403"])

    def test_an_unverified_account_cannot_sign_in(self, api: APIClient) -> None:
        sign_up(api)

        response = api.post(
            LOGIN, {"identifier": EMAIL, "password": PASSWORD}, format="json"
        )

        assert response.status_code == 403
        assert first_error(response)["code"] == "account_not_verified"
        assert not CustomerSession.objects.exists()

    def test_an_unverified_account_with_a_wrong_password_is_still_just_a_401(
        self, api: APIClient
    ) -> None:
        sign_up(api)

        response = api.post(
            LOGIN, {"identifier": EMAIL, "password": "wrong-password-1"}, format="json"
        )

        assert (
            response.status_code == 401
        )  # the state is revealed only to who knows the password

    def test_a_blocked_customer_is_permission_denied(self, api: APIClient) -> None:
        verified_customer(api)
        Customer.objects.update(is_blocked=True)

        response = api.post(
            LOGIN, {"identifier": EMAIL, "password": PASSWORD}, format="json"
        )

        assert response.status_code == 403
        assert first_error(response)["code"] == "permission_denied"

    def test_a_deactivated_account_is_permission_denied(self, api: APIClient) -> None:
        verified_customer(api)
        User.objects.update(is_active=False)

        response = api.post(
            LOGIN, {"identifier": EMAIL, "password": PASSWORD}, format="json"
        )

        assert response.status_code == 403

    def test_a_staff_account_cannot_sign_in_here(self, api: APIClient) -> None:
        User.objects.create_user(
            "cashier1", "pw-for-tests-123", email="cashier@example.com"
        )

        response = api.post(
            LOGIN,
            {"identifier": "cashier@example.com", "password": "pw-for-tests-123"},
            format="json",
        )

        assert response.status_code == 401

    def test_ten_tries_for_one_contact_then_it_waits(self, api: APIClient) -> None:
        verified_customer(api)
        for _ in range(10):
            api.post(
                LOGIN,
                {"identifier": EMAIL, "password": "wrong-password-1"},
                format="json",
            )

        response = api.post(
            LOGIN, {"identifier": EMAIL, "password": PASSWORD}, format="json"
        )

        assert response.status_code == 429
        assert first_error(response)["code"] == "throttled"

    def test_a_good_sign_in_clears_the_count(self, api: APIClient) -> None:
        verified_customer(api)
        for _ in range(8):
            api.post(
                LOGIN,
                {"identifier": EMAIL, "password": "wrong-password-1"},
                format="json",
            )
        assert (
            api.post(
                LOGIN, {"identifier": EMAIL, "password": PASSWORD}, format="json"
            ).status_code
            == 200
        )

        for _ in range(8):
            api.post(
                LOGIN,
                {"identifier": EMAIL, "password": "wrong-password-1"},
                format="json",
            )

        assert (
            api.post(
                LOGIN, {"identifier": EMAIL, "password": PASSWORD}, format="json"
            ).status_code
            == 200
        )

    def test_the_count_is_per_contact(self, api: APIClient) -> None:
        verified_customer(api)
        for _ in range(10):
            api.post(
                LOGIN,
                {"identifier": "other@example.com", "password": "x-wrong-password"},
                format="json",
            )

        assert (
            api.post(
                LOGIN, {"identifier": EMAIL, "password": PASSWORD}, format="json"
            ).status_code
            == 200
        )


# --- sign out and the profile ---------------------------------------------------------------


class TestSessionAndProfile:
    def test_logout_revokes_this_token_and_only_this_one(self, api: APIClient) -> None:
        first, _ = verified_customer(api)
        second = api.post(
            LOGIN, {"identifier": EMAIL, "password": PASSWORD}, format="json"
        ).json()["token"]

        response = api.post(LOGOUT, headers=customer_headers(first))

        assert response.status_code == 204 and not response.content
        assert api.get(ME, headers=customer_headers(first)).status_code == 401
        assert api.get(ME, headers=customer_headers(second)).status_code == 200

    def test_the_profile_needs_a_token(self, api: APIClient) -> None:
        response = api.get(ME)

        assert response.status_code == 401
        assert first_error(response)["code"] == "not_authenticated"
        assert response["WWW-Authenticate"] == "Customer"

    @pytest.mark.parametrize(
        "header", ["Customer wrong-token", "Customer", "Token abc"]
    )
    def test_a_bad_or_foreign_token_is_a_401(self, api: APIClient, header: str) -> None:
        assert api.get(ME, headers={"Authorization": header}).status_code == 401

    def test_a_staff_token_does_not_open_a_customer_call(self, api: APIClient) -> None:
        from rest_framework.authtoken.models import Token

        user = User.objects.create_user("cashier1", "pw-for-tests-123")
        token = Token.objects.create(user=user)

        assert (
            api.get(ME, headers={"Authorization": f"Token {token.key}"}).status_code
            == 401
        )

    def test_logout_without_a_token_is_a_401(self, api: APIClient) -> None:
        assert api.post(LOGOUT).status_code == 401

    def test_the_profile_shows_each_contact_and_whether_it_is_verified(
        self, api: APIClient
    ) -> None:
        token, _ = verified_customer(api)

        body = api.get(ME, headers=customer_headers(token)).json()

        assert body["email"] == EMAIL and body["email_verified"] is True
        assert body["phone"] is None and body["phone_verified"] is False
        assert set(body) == {
            "id",
            "full_name",
            "locale",
            "email",
            "email_verified",
            "phone",
            "phone_verified",
        }
        assert "password" not in str(body)


# --- add the missing contact ----------------------------------------------------------------


class TestAddContact:
    def test_a_phone_is_added_with_a_code_and_saved_only_after_it(
        self, api: APIClient
    ) -> None:
        token, _ = verified_customer(api)
        headers = customer_headers(token)

        sent = api.post(
            CONTACT, {"phone": "050 000 0002"}, format="json", headers=headers
        )

        assert sent.status_code == 202
        assert (
            sent.json()["identifier"] == "+971500000002"
            and sent.json()["channel"] == "sms"
        )
        assert User.objects.get(email=EMAIL).phone is None  # not saved yet
        confirmed = api.post(
            CONTACT_VERIFY,
            {"code": last_code("+971500000002")},
            format="json",
            headers=headers,
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["phone"] == "+971500000002"
        assert confirmed.json()["phone_verified"] is True
        assert confirmed.json()["email"] == EMAIL

    def test_an_email_is_added_to_a_phone_account(self, api: APIClient) -> None:
        sign_up(api, email=None, phone=PHONE)
        api.post(VERIFY, {"identifier": PHONE, "code": last_code(PHONE)}, format="json")
        token = api.post(
            LOGIN, {"identifier": PHONE, "password": PASSWORD}, format="json"
        ).json()["token"]
        headers = customer_headers(token)

        api.post(
            CONTACT, {"email": "sara.work@example.com"}, format="json", headers=headers
        )
        confirmed = api.post(
            CONTACT_VERIFY,
            {"code": last_code("sara.work@example.com")},
            format="json",
            headers=headers,
        )

        assert confirmed.json()["email"] == "sara.work@example.com"
        assert confirmed.json()["email_verified"] is True

    def test_a_contact_the_account_already_has_cannot_be_changed(
        self, api: APIClient
    ) -> None:
        token, _ = verified_customer(api)

        response = api.post(
            CONTACT,
            {"email": "other@example.com"},
            format="json",
            headers=customer_headers(token),
        )

        assert response.status_code == 409
        assert first_error(response)["code"] == "contact_already_set"

    def test_a_contact_that_belongs_to_another_account_is_account_exists(
        self, api: APIClient
    ) -> None:
        verified_customer(
            api, email="omar.example@example.com", full_name="Omar Example"
        )
        other_api = APIClient()
        sign_up(other_api, email=None, phone=PHONE)
        other_api.post(
            VERIFY, {"identifier": PHONE, "code": last_code(PHONE)}, format="json"
        )
        token = other_api.post(
            LOGIN, {"identifier": PHONE, "password": PASSWORD}, format="json"
        ).json()["token"]

        response = other_api.post(
            CONTACT,
            {"email": "omar.example@example.com"},
            format="json",
            headers=customer_headers(token),
        )

        assert response.status_code == 409
        assert first_error(response)["code"] == "account_exists"

    @pytest.mark.parametrize("body", [{}, {"email": "a@example.com", "phone": PHONE}])
    def test_exactly_one_contact_is_required(
        self, api: APIClient, body: dict[str, str]
    ) -> None:
        token, _ = verified_customer(api)

        response = api.post(
            CONTACT, body, format="json", headers=customer_headers(token)
        )

        assert response.status_code == 400
        assert "contact_required" in codes(response)

    def test_a_wrong_code_does_not_save_the_contact(self, api: APIClient) -> None:
        token, _ = verified_customer(api)
        headers = customer_headers(token)
        api.post(CONTACT, {"phone": "050 000 0002"}, format="json", headers=headers)
        good = last_code("+971500000002")

        response = api.post(
            CONTACT_VERIFY,
            {"code": "000000" if good != "000000" else "111111"},
            format="json",
            headers=headers,
        )

        assert (
            response.status_code == 400
            and first_error(response)["code"] == "code_invalid"
        )
        assert User.objects.get(email=EMAIL).phone is None

    def test_verifying_with_nothing_pending_is_no_pending_contact(
        self, api: APIClient
    ) -> None:
        token, _ = verified_customer(api)

        response = api.post(
            CONTACT_VERIFY,
            {"code": "123456"},
            format="json",
            headers=customer_headers(token),
        )

        assert response.status_code == 409
        assert first_error(response)["code"] == "no_pending_contact"

    def test_the_contact_is_taken_by_someone_else_before_the_code_is_used(
        self, api: APIClient
    ) -> None:
        token, _ = verified_customer(api)
        headers = customer_headers(token)
        api.post(CONTACT, {"phone": "050 000 0002"}, format="json", headers=headers)
        User.objects.create_user("someone", "pw-for-tests-123", phone="+971500000002")

        response = api.post(
            CONTACT_VERIFY,
            {"code": last_code("+971500000002")},
            format="json",
            headers=headers,
        )

        assert response.status_code == 409
        assert first_error(response)["code"] == "account_exists"
        assert User.objects.get(email=EMAIL).phone is None

    def test_both_calls_need_a_customer_token(self, api: APIClient) -> None:
        assert api.post(CONTACT, {"phone": PHONE}, format="json").status_code == 401
        assert (
            api.post(CONTACT_VERIFY, {"code": "123456"}, format="json").status_code
            == 401
        )

    def test_one_customers_pending_code_is_not_another_customers(
        self, api: APIClient
    ) -> None:
        token, _ = verified_customer(api)
        api.post(
            CONTACT,
            {"phone": "050 000 0002"},
            format="json",
            headers=customer_headers(token),
        )
        code = last_code("+971500000002")
        other_api = APIClient()
        other_token, _ = verified_customer(
            other_api, email="omar.example@example.com", full_name="Omar Example"
        )

        response = other_api.post(
            CONTACT_VERIFY,
            {"code": code},
            format="json",
            headers=customer_headers(other_token),
        )

        assert response.status_code == 409  # nothing pending for Omar


# --- forgotten password ---------------------------------------------------------------------


class TestPasswordReset:
    def test_the_verified_contact_gets_a_code_and_the_answer_is_generic(
        self, api: APIClient
    ) -> None:
        verified_customer(api)
        before = len(sent_messages(EMAIL))

        response = api.post(RESET, {"identifier": EMAIL}, format="json")

        assert response.status_code == 202
        assert response.json() == {"code_expires_in_seconds": 600}
        assert len(sent_messages(EMAIL)) == before + 1
        assert "reset" in sent_messages(EMAIL)[-1].body.lower()

    def test_an_unknown_contact_gets_exactly_the_same_answer_and_nothing_is_sent(
        self, api: APIClient
    ) -> None:
        response = api.post(RESET, {"identifier": "nobody@example.com"}, format="json")

        assert response.status_code == 202
        assert response.json() == {"code_expires_in_seconds": 600}
        assert not OutboxMessage.objects.exists()

    def test_an_unverified_contact_gets_no_code(self, api: APIClient) -> None:
        sign_up(api)
        before = len(sent_messages())

        response = api.post(RESET, {"identifier": EMAIL}, format="json")

        assert response.status_code == 202
        assert len(sent_messages()) == before

    def test_a_second_request_within_a_minute_is_throttled_for_every_contact(
        self, api: APIClient
    ) -> None:
        for identifier in (EMAIL, "nobody@example.com"):
            assert (
                api.post(RESET, {"identifier": identifier}, format="json").status_code
                == 202
            )
            again = api.post(RESET, {"identifier": identifier}, format="json")
            assert again.status_code == 429
            assert 1 <= int(again["Retry-After"]) <= 61

    def test_the_code_sets_a_new_password_and_signs_every_device_out(
        self, api: APIClient
    ) -> None:
        token, _ = verified_customer(api)
        other = api.post(
            LOGIN, {"identifier": EMAIL, "password": PASSWORD}, format="json"
        ).json()["token"]
        api.post(RESET, {"identifier": EMAIL}, format="json")

        response = api.post(
            RESET_CONFIRM,
            {
                "identifier": EMAIL,
                "code": last_code(EMAIL),
                "new_password": NEW_PASSWORD,
            },
            format="json",
        )

        assert response.status_code == 204
        assert api.get(ME, headers=customer_headers(token)).status_code == 401
        assert api.get(ME, headers=customer_headers(other)).status_code == 401
        assert (
            api.post(
                LOGIN, {"identifier": EMAIL, "password": PASSWORD}, format="json"
            ).status_code
            == 401
        )
        assert (
            api.post(
                LOGIN, {"identifier": EMAIL, "password": NEW_PASSWORD}, format="json"
            ).status_code
            == 200
        )

    def test_a_weak_new_password_is_a_400_and_does_not_spend_the_code(
        self, api: APIClient
    ) -> None:
        verified_customer(api)
        api.post(RESET, {"identifier": EMAIL}, format="json")
        code = last_code(EMAIL)

        weak = api.post(
            RESET_CONFIRM,
            {"identifier": EMAIL, "code": code, "new_password": "short1"},
            format="json",
        )
        again = api.post(
            RESET_CONFIRM,
            {"identifier": EMAIL, "code": code, "new_password": NEW_PASSWORD},
            format="json",
        )

        assert weak.status_code == 400
        assert any(
            e["code"] == "password_too_short" and e["attr"] == "new_password"
            for e in weak.json()["errors"]
        )
        assert again.status_code == 204

    def test_a_code_works_once(self, api: APIClient) -> None:
        verified_customer(api)
        api.post(RESET, {"identifier": EMAIL}, format="json")
        body = {
            "identifier": EMAIL,
            "code": last_code(EMAIL),
            "new_password": NEW_PASSWORD,
        }
        assert api.post(RESET_CONFIRM, body, format="json").status_code == 204

        again = api.post(
            RESET_CONFIRM,
            {**body, "new_password": "yet-another-passphrase-3"},
            format="json",
        )

        assert again.status_code == 400 and first_error(again)["code"] == "code_invalid"

    def test_a_wrong_expired_or_unknown_is_refused(self, api: APIClient) -> None:
        verified_customer(api)
        api.post(RESET, {"identifier": EMAIL}, format="json")
        good = last_code(EMAIL)
        wrong = "000000" if good != "000000" else "111111"

        bad = api.post(
            RESET_CONFIRM,
            {"identifier": EMAIL, "code": wrong, "new_password": NEW_PASSWORD},
            format="json",
        )
        unknown = api.post(
            RESET_CONFIRM,
            {
                "identifier": "nobody@example.com",
                "code": good,
                "new_password": NEW_PASSWORD,
            },
            format="json",
        )
        VerificationCode.objects.update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        expired = api.post(
            RESET_CONFIRM,
            {"identifier": EMAIL, "code": good, "new_password": NEW_PASSWORD},
            format="json",
        )

        assert first_error(bad)["code"] == "code_invalid"
        assert first_error(unknown)["code"] == "code_invalid"
        assert first_error(expired)["code"] == "code_expired"
        assert User.objects.get(email=EMAIL).check_password(PASSWORD)

    def test_five_wrong_codes_then_too_many_attempts(self, api: APIClient) -> None:
        verified_customer(api)
        api.post(RESET, {"identifier": EMAIL}, format="json")
        good = last_code(EMAIL)
        wrong = "000000" if good != "000000" else "111111"
        for _ in range(5):
            api.post(
                RESET_CONFIRM,
                {"identifier": EMAIL, "code": wrong, "new_password": NEW_PASSWORD},
                format="json",
            )

        response = api.post(
            RESET_CONFIRM,
            {"identifier": EMAIL, "code": good, "new_password": NEW_PASSWORD},
            format="json",
        )

        assert response.status_code == 429
        assert first_error(response)["code"] == "too_many_attempts"

    def test_a_sign_up_code_does_not_reset_a_password(self, api: APIClient) -> None:
        sign_up(api)
        code = last_code(EMAIL)

        response = api.post(
            RESET_CONFIRM,
            {"identifier": EMAIL, "code": code, "new_password": NEW_PASSWORD},
            format="json",
        )

        assert response.status_code == 400
        assert User.objects.get(email=EMAIL).check_password(PASSWORD)

    def test_a_reset_for_a_phone_goes_by_sms(self, api: APIClient) -> None:
        sign_up(api, email=None, phone=PHONE)
        api.post(VERIFY, {"identifier": PHONE, "code": last_code(PHONE)}, format="json")

        api.post(RESET, {"identifier": "050 000 0001"}, format="json")

        assert sent_messages(PHONE)[-1].channel == "sms"


# --- throttles and privacy ------------------------------------------------------------------


class TestThrottlesAndPrivacy:
    @pytest.mark.parametrize(
        ("scope", "path", "body"),
        [
            ("customer_signup", SIGNUP, {}),
            ("customer_verify", VERIFY, {}),
            ("customer_resend", RESEND, {}),
            ("customer_login", LOGIN, {}),
            ("customer_reset", RESET, {}),
            ("customer_reset_confirm", RESET_CONFIRM, {}),
        ],
    )
    def test_every_public_call_has_its_own_throttle(
        self,
        api: APIClient,
        monkeypatch: pytest.MonkeyPatch,
        scope: str,
        path: str,
        body: dict[str, Any],
    ) -> None:
        monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {scope: "2/min"})

        statuses = [api.post(path, body, format="json").status_code for _ in range(3)]

        assert statuses[:2] != [429, 429] and statuses[2] == 429

    def test_the_signed_in_contact_calls_are_throttled_too(
        self, api: APIClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        token, _ = verified_customer(api)
        monkeypatch.setattr(
            ScopedRateThrottle, "THROTTLE_RATES", {"customer_contact": "2/min"}
        )

        statuses = [
            api.post(
                CONTACT, {}, format="json", headers=customer_headers(token)
            ).status_code
            for _ in range(3)
        ]

        assert statuses[2] == 429

    def test_the_real_rates_are_set_for_every_scope(self) -> None:
        from django.conf import settings

        rates: dict[str, str] = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]  # type: ignore[assignment]
        for scope in (
            "customer_signup",
            "customer_verify",
            "customer_resend",
            "customer_login",
            "customer_contact",
            "customer_reset",
            "customer_reset_confirm",
        ):
            assert scope in rates

    def test_no_code_password_or_contact_reaches_the_logs(
        self, api: APIClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG):
            sign_up(api)
            code = last_code(EMAIL)
            api.post(VERIFY, {"identifier": EMAIL, "code": code}, format="json")
            api.post(
                LOGIN,
                {"identifier": EMAIL, "password": "wrong-password-1"},
                format="json",
            )
            api.post(RESET, {"identifier": EMAIL}, format="json")

        for secret in (code, PASSWORD, "wrong-password-1", "sara.example"):
            assert secret not in caplog.text

    def test_the_hashes_hold_no_plain_code_in_the_database(
        self, api: APIClient
    ) -> None:
        sign_up(api)
        code = last_code(EMAIL)

        for row in VerificationCode.objects.values():
            assert code not in str(row)

    def test_every_answer_carries_a_request_id_and_no_store(
        self, api: APIClient
    ) -> None:
        for path, body in ((SIGNUP, {}), (LOGIN, {}), (RESET, {"identifier": EMAIL})):
            response = api.post(path, body, format="json")
            assert response["Cache-Control"] == "no-store"
            assert response["X-Request-ID"]
