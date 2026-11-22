from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from customers.errors import PhoneNotVerified
from customers.models import Customer, CustomerSession
from customers.services import (
    TOUCH_INTERVAL,
    ensure_phone_verified_for_order,
    generate_token,
    get_active_session,
    hash_token,
    revoke_all_sessions,
    revoke_session,
    start_session,
    touch_session,
)
from customers.tests.factories import make_customer

pytestmark = pytest.mark.django_db


def test_tokens_are_long_and_different_each_time() -> None:
    first, second = generate_token(), generate_token()

    assert first != second
    assert len(first) >= 43


def test_the_hash_is_a_sha256_hex_digest() -> None:
    digest = hash_token("abc")

    assert digest == hash_token("abc")
    assert digest != hash_token("abd")
    assert len(digest) == 64
    assert digest == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_a_started_session_stores_only_the_hash() -> None:
    session, token = start_session(make_customer(), "Chrome on Android")

    assert session.token_hash == hash_token(token)
    assert token not in {session.token_hash, session.user_agent}
    assert CustomerSession.objects.filter(token_hash=token).count() == 0
    assert session.user_agent == "Chrome on Android"
    assert session.last_seen_at is not None


def test_a_long_user_agent_is_cut() -> None:
    session, _ = start_session(make_customer(), "x" * 400)

    assert len(session.user_agent) == 255


def test_a_token_finds_its_session() -> None:
    customer = make_customer()
    session, token = start_session(customer)

    found = get_active_session(token)

    assert found is not None
    assert found.pk == session.pk
    assert found.customer.user == customer.user


def test_an_unknown_token_finds_nothing() -> None:
    start_session(make_customer())

    assert get_active_session("not-a-real-token") is None


def test_a_revoked_session_finds_nothing() -> None:
    session, token = start_session(make_customer())

    revoke_session(session)

    assert get_active_session(token) is None
    session.refresh_from_db()
    assert session.is_active is False


def test_revoking_twice_keeps_the_first_time() -> None:
    session, _ = start_session(make_customer())
    revoke_session(session)
    first = session.revoked_at

    revoke_session(session)

    assert session.revoked_at == first


def test_signing_out_everywhere_revokes_every_session_of_that_customer_only() -> None:
    sara, omar = make_customer("sara@example.com"), make_customer("omar@example.com")
    _, sara_one = start_session(sara)
    _, sara_two = start_session(sara)
    _, omar_token = start_session(omar)

    assert revoke_all_sessions(sara) == 2

    assert get_active_session(sara_one) is None
    assert get_active_session(sara_two) is None
    assert get_active_session(omar_token) is not None


def test_last_seen_is_refreshed_only_after_the_interval() -> None:
    customer = make_customer()
    session, _ = start_session(customer)
    recent = session.last_seen_at

    touch_session(session)
    session.refresh_from_db()
    assert session.last_seen_at == recent

    old = timezone.now() - TOUCH_INTERVAL - timedelta(seconds=1)
    CustomerSession.objects.filter(pk=session.pk).update(last_seen_at=old)
    session.refresh_from_db()
    touch_session(session)

    session.refresh_from_db()
    assert session.last_seen_at is not None
    assert session.last_seen_at > old
    customer = Customer.objects.get(pk=customer.pk)
    assert customer.last_seen_at is not None


class TestPhoneGate:
    def test_it_is_off_by_default(self, settings: Any) -> None:
        assert settings.REQUIRE_VERIFIED_PHONE is False

        ensure_phone_verified_for_order(make_customer())

    def test_an_unverified_phone_is_refused_when_it_is_on(self, settings: Any) -> None:
        settings.REQUIRE_VERIFIED_PHONE = True

        with pytest.raises(PhoneNotVerified) as refused:
            ensure_phone_verified_for_order(make_customer())

        assert refused.value.status_code == 403
        assert refused.value.get_codes() == "phone_not_verified"

    def test_a_verified_phone_passes_when_it_is_on(self, settings: Any) -> None:
        settings.REQUIRE_VERIFIED_PHONE = True
        customer = make_customer()
        customer.user.phone = "+971501234567"
        customer.user.phone_verified_at = timezone.now()
        customer.user.save()

        ensure_phone_verified_for_order(customer)

    def test_a_refusal_changes_nothing(self, settings: Any) -> None:
        settings.REQUIRE_VERIFIED_PHONE = True
        customer = make_customer()

        with pytest.raises(PhoneNotVerified):
            ensure_phone_verified_for_order(customer)

        customer.user.refresh_from_db()
        assert customer.user.phone_verified_at is None
