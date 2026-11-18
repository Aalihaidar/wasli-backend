"""The life of a verification code: stored hashed, expiring, limited, replaced, spent once."""

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from django.utils import timezone
from rest_framework.exceptions import Throttled

from customers import verification as v
from customers.errors import CodeExpired, CodeInvalid, TooManyAttempts
from customers.models import Customer, VerificationCode
from customers.tests.factories import make_customer
from customers.tests.helpers import last_code, sent_messages
from messaging.models import Channel, OutboxMessage
from users.models import User

pytestmark = pytest.mark.django_db

Purpose = VerificationCode.Purpose


def issue(user: User, **extra: Any) -> VerificationCode:
    values = {
        "user": user,
        "purpose": Purpose.SIGNUP,
        "channel": Channel.EMAIL.value,
        "identifier": "sara@example.com",
        "locale": "en",
        **extra,
    }
    return v.issue_code(**values)


@pytest.fixture
def customer() -> Customer:
    return make_customer("sara@example.com")


class TestIssuing:
    def test_the_code_is_six_digits_and_sent_to_the_contact(
        self, customer: Customer
    ) -> None:
        issue(customer.user)

        [message] = sent_messages()
        assert message.recipient == "sara@example.com"
        assert message.channel == "email"
        assert message.purpose == "verification"
        assert len(last_code()) == 6

    def test_only_a_keyed_hash_is_stored_never_the_code(
        self, customer: Customer
    ) -> None:
        row = issue(customer.user)
        code = last_code()

        assert code not in row.code_hash
        assert row.code_hash == v.hash_code(row.pk, code)
        assert len(row.code_hash) == 64
        for value in VerificationCode.objects.values_list(
            "code_hash", "identifier", "purpose"
        ):
            assert code not in " ".join(value)

    def test_the_hash_depends_on_the_row_and_on_the_secret_key(
        self, customer: Customer, settings: Any
    ) -> None:
        row = issue(customer.user)
        code = last_code()

        assert v.hash_code(row.pk, code) != v.hash_code(issue_id_other(), code)
        settings.SECRET_KEY = "another-secret-key-for-this-test-only-0123456789"
        assert v.hash_code(row.pk, code) != row.code_hash

    def test_it_expires_in_ten_minutes(self, customer: Customer) -> None:
        now = timezone.now()

        row = issue(customer.user, now=now)

        assert row.expires_at == now + timedelta(minutes=10)

    def test_a_new_code_replaces_the_open_one(self, customer: Customer) -> None:
        first = issue(customer.user)
        second = issue(customer.user, enforce_limits=False)

        first.refresh_from_db()
        assert first.invalidated_at is not None
        assert second.invalidated_at is None
        assert v.latest_open_code(customer.user, Purpose.SIGNUP) == second

    def test_codes_of_different_purposes_do_not_replace_each_other(
        self, customer: Customer
    ) -> None:
        signup = issue(customer.user)
        reset = issue(customer.user, purpose=Purpose.PASSWORD_RESET)

        signup.refresh_from_db()
        assert signup.invalidated_at is None
        assert reset.purpose == Purpose.PASSWORD_RESET
        assert sent_messages()[-1].purpose == "password_reset"

    def test_an_sms_has_no_subject_and_an_email_has_one(
        self, customer: Customer
    ) -> None:
        issue(customer.user)
        issue(
            customer.user,
            purpose=Purpose.CONTACT,
            channel=Channel.SMS.value,
            identifier="+971500000009",
        )

        email, sms = sent_messages()
        assert email.subject and not sms.subject

    def test_nothing_is_saved_when_the_message_cannot_be_sent(
        self, customer: Customer, settings: Any
    ) -> None:
        from django.core.exceptions import ImproperlyConfigured

        settings.MESSAGING_BACKEND = "disabled"

        with pytest.raises(ImproperlyConfigured):
            issue(customer.user)

        assert not VerificationCode.objects.exists()


def issue_id_other() -> UUID:
    import uuid

    return uuid.uuid4()


class TestSendLimits:
    def test_a_second_code_within_a_minute_is_refused_with_the_wait(
        self, customer: Customer
    ) -> None:
        issue(customer.user)

        with pytest.raises(Throttled) as refused:
            issue(customer.user)

        assert 1 <= refused.value.wait <= 60
        assert OutboxMessage.objects.count() == 1

    def test_after_a_minute_a_new_code_is_allowed(self, customer: Customer) -> None:
        row = issue(customer.user)
        VerificationCode.objects.filter(pk=row.pk).update(
            created_at=timezone.now() - timedelta(seconds=61)
        )

        issue(customer.user)

        assert OutboxMessage.objects.count() == 2

    def test_five_an_hour_then_the_sixth_waits(self, customer: Customer) -> None:
        now = timezone.now()
        for minutes_ago in (50, 40, 30, 20, 10):
            VerificationCode.objects.create(
                user=customer.user,
                purpose=Purpose.SIGNUP,
                channel="email",
                identifier="sara@example.com",
                code_hash="x" * 64,
                expires_at=now,
            )
            VerificationCode.objects.filter(code_hash="x" * 64).update(
                created_at=now - timedelta(minutes=minutes_ago),
                code_hash="y" * 64,
            )

        with pytest.raises(Throttled) as refused:
            issue(customer.user)

        assert (
            9 * 60 <= refused.value.wait <= 10 * 60 + 1
        )  # when the oldest leaves the hour

    def test_the_limits_are_per_contact_and_per_purpose(
        self, customer: Customer
    ) -> None:
        issue(customer.user)

        issue(customer.user, identifier="other@example.com")
        issue(customer.user, purpose=Purpose.PASSWORD_RESET)

        assert OutboxMessage.objects.count() == 3

    def test_a_reset_may_skip_the_database_limits(self, customer: Customer) -> None:
        issue(customer.user, purpose=Purpose.PASSWORD_RESET, enforce_limits=False)
        issue(customer.user, purpose=Purpose.PASSWORD_RESET, enforce_limits=False)

        assert OutboxMessage.objects.count() == 2


class TestChecking:
    def check(self, customer: Customer, code: str, **extra: Any) -> VerificationCode:
        values = {
            "user": customer.user,
            "purpose": Purpose.SIGNUP,
            "identifier": "sara@example.com",
            "submitted": code,
            **extra,
        }
        return v.check_code(**values)

    def test_the_right_code_is_accepted_once(self, customer: Customer) -> None:
        issue(customer.user)
        code = last_code()

        row = self.check(customer, code)

        assert row.consumed_at is not None
        with pytest.raises(CodeInvalid):
            self.check(customer, code)  # spent: nothing is open any more

    def test_a_wrong_code_counts_an_attempt_that_survives_the_error(
        self, customer: Customer
    ) -> None:
        row = issue(customer.user)

        with pytest.raises(CodeInvalid):
            self.check(customer, "000000" if last_code() != "000000" else "111111")

        row.refresh_from_db()
        assert row.attempts == 1

    def test_five_wrong_attempts_kill_the_code_even_for_the_right_one(
        self, customer: Customer
    ) -> None:
        issue(customer.user)
        good = last_code()
        wrong = "000000" if good != "000000" else "111111"
        for _ in range(v.MAX_ATTEMPTS):
            with pytest.raises(CodeInvalid):
                self.check(customer, wrong)

        with pytest.raises(TooManyAttempts):
            self.check(customer, good)

    def test_an_expired_code_is_refused(self, customer: Customer) -> None:
        issue(customer.user, now=timezone.now() - timedelta(minutes=11))

        with pytest.raises(CodeExpired):
            self.check(customer, last_code())

    def test_a_replaced_code_no_longer_works(self, customer: Customer) -> None:
        first = issue(customer.user, now=timezone.now() - timedelta(minutes=5))
        old = last_code()
        VerificationCode.objects.filter(pk=first.pk).update(
            created_at=timezone.now() - timedelta(minutes=5)
        )
        issue(customer.user)

        if old != last_code():
            with pytest.raises(CodeInvalid):
                self.check(customer, old)

    def test_a_code_for_another_contact_does_not_work(self, customer: Customer) -> None:
        issue(customer.user)

        with pytest.raises(CodeInvalid):
            self.check(customer, last_code(), identifier="other@example.com")

    def test_a_code_for_another_purpose_does_not_work(self, customer: Customer) -> None:
        issue(customer.user)

        with pytest.raises(CodeInvalid):
            self.check(customer, last_code(), purpose=Purpose.PASSWORD_RESET)

    def test_another_users_code_does_not_work(self, customer: Customer) -> None:
        other = make_customer("omar@example.com")
        issue(customer.user)

        with pytest.raises(CodeInvalid):
            v.check_code(
                user=other.user,
                purpose=Purpose.SIGNUP,
                identifier="sara@example.com",
                submitted=last_code(),
            )

    def test_checking_without_spending_leaves_the_code_open(
        self, customer: Customer
    ) -> None:
        row = issue(customer.user, purpose=Purpose.PASSWORD_RESET)

        checked = self.check(
            customer, last_code(), purpose=Purpose.PASSWORD_RESET, consume=False
        )

        assert checked.pk == row.pk and checked.consumed_at is None
        v.mark_consumed(checked)
        checked.refresh_from_db()
        assert checked.consumed_at is not None
