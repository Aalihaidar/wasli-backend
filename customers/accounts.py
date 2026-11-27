"""The customer-account flows: sign up, verify, resend, sign in, add a contact, reset the password.

A customer has a ``users.User`` (the credentials and the contacts) and a ``Customer`` (the
profile). The contact given at sign-up is verified by a code; sign-in needs it. Views stay thin
and call these functions.
"""

from dataclasses import dataclass
from datetime import datetime

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from messaging.models import Channel
from users.identifiers import identify
from users.models import User
from users.passwords import check_password_strength

from . import limits
from .errors import (
    AccountExists,
    AccountNotVerified,
    CodeInvalid,
    ContactAlreadySet,
    InvalidCredentials,
    NoPendingContact,
)
from .models import Customer
from .services import revoke_all_sessions, start_session
from .verification import (
    CODE_TTL,
    RESEND_WAIT,
    Purpose,
    check_code,
    issue_code,
    latest_open_code,
    mark_consumed,
)

CODE_EXPIRES_IN = int(CODE_TTL.total_seconds())
RESEND_IN = int(RESEND_WAIT.total_seconds())

# Wrong passwords for one contact before it is refused for a while.
LOGIN_FAILURES = 10
LOGIN_WINDOW_SECONDS = 15 * 60
# Reset codes for one contact: one a minute, five an hour, whether or not the account exists.
RESET_COOLDOWN_SECONDS = 60
RESET_PER_HOUR = 5
RESET_CONFIRM_ATTEMPTS = 10


@dataclass(frozen=True)
class SentCode:
    identifier: str
    channel: str
    code_expires_in_seconds: int = CODE_EXPIRES_IN
    resend_available_in_seconds: int = RESEND_IN


def _channel(kind: str) -> str:
    return Channel.EMAIL.value if kind == "email" else Channel.SMS.value


def contact_of(value: str) -> tuple[str, str] | None:
    """The kind (``email`` or ``phone``) and the normalised value of a contact; ``None`` for
    anything else, a username included: a customer has none."""
    found = identify(value)
    if found is None or found[0] not in ("email", "phone"):
        return None
    return found


def customer_with(kind: str, value: str) -> Customer | None:
    return (
        Customer.objects.select_related("user")
        .filter(**{f"user__{kind}": value})
        .first()
    )


def contact_verified(user: User, kind: str) -> bool:
    return (
        user.email_verified_at if kind == "email" else user.phone_verified_at
    ) is not None


def _mark_verified(user: User, kind: str, now: datetime) -> None:
    field = "email_verified_at" if kind == "email" else "phone_verified_at"
    setattr(user, field, now)
    user.save(update_fields=[field, "updated_at"])


# --- sign up and verify ---------------------------------------------------------------------


def sign_up(
    *, full_name: str, kind: str, value: str, password: str, locale: str
) -> SentCode:
    """Create an unverified account and send its code.

    A contact whose account is still unverified restarts the sign-up (new name, new password,
    new code), so an abandoned attempt never locks someone out of their own contact. A contact
    of a verified account, a staff account or the platform team is ``account_exists``.
    """
    with transaction.atomic():
        existing = User.objects.filter(**{kind: value}).first()
        if existing is None:
            try:
                user = User.objects.create_user(
                    None,
                    password,
                    email=value if kind == "email" else None,
                    phone=value if kind == "phone" else None,
                    full_name=full_name,
                )
                Customer.objects.create(
                    user=user, display_name=full_name, locale=locale
                )
            except DjangoValidationError, IntegrityError:
                raise AccountExists from None
        else:
            customer = Customer.objects.filter(user=existing).first()
            if (
                customer is None
                or existing.is_staff
                or existing.is_superuser
                or contact_verified(existing, kind)
            ):
                raise AccountExists
            user = existing
            user.full_name = full_name
            user.set_password(password)
            user.save(update_fields=["full_name", "password", "updated_at"])
            customer.display_name = full_name
            customer.locale = locale
            customer.save(update_fields=["display_name", "locale", "updated_at"])
        issue_code(
            user=user,
            purpose=Purpose.SIGNUP,
            channel=_channel(kind),
            identifier=value,
            locale=locale,
        )
    return SentCode(identifier=value, channel=_channel(kind))


def _refuse_if_closed(customer: Customer) -> None:
    if customer.is_blocked or not customer.user.is_active:
        raise PermissionDenied()


def verify_signup(
    *, kind: str, value: str, code: str, user_agent: str = ""
) -> tuple[Customer, str]:
    """Check the sign-up code, mark the contact verified and open the first session."""
    customer = customer_with(kind, value)
    if customer is None:
        raise CodeInvalid
    _refuse_if_closed(customer)
    check_code(
        user=customer.user, purpose=Purpose.SIGNUP, identifier=value, submitted=code
    )
    _mark_verified(customer.user, kind, timezone.now())
    _, token = start_session(customer, user_agent)
    return customer, token


def resend_code(*, kind: str, value: str) -> SentCode:
    """A new sign-up code for an unverified account. Any other contact gets the same answer and
    nothing is sent, so the call reveals nothing about who has an account."""
    sent = SentCode(identifier=value, channel=_channel(kind))
    customer = customer_with(kind, value)
    if customer is None or contact_verified(customer.user, kind) or customer.is_blocked:
        return sent
    issue_code(
        user=customer.user,
        purpose=Purpose.SIGNUP,
        channel=_channel(kind),
        identifier=value,
        locale=customer.locale,
    )
    return sent


# --- sign in --------------------------------------------------------------------------------


def log_in(
    *, identifier: str, password: str, user_agent: str = ""
) -> tuple[Customer, str]:
    contact = contact_of(identifier)
    key = limits.key_for(
        "login", f"{contact[0]}:{contact[1]}" if contact else identifier.strip().lower()
    )
    limits.hit(key, limit=LOGIN_FAILURES, window_seconds=LOGIN_WINDOW_SECONDS)
    customer = customer_with(*contact) if contact else None
    if customer is None:
        # Hash once anyway, so an unknown contact takes as long as a wrong password.
        User().set_password(password)
        raise InvalidCredentials
    user = customer.user
    if not user.check_password(password):
        raise InvalidCredentials
    assert contact is not None  # noqa: S101
    _refuse_if_closed(customer)
    if not contact_verified(user, contact[0]):
        raise AccountNotVerified
    limits.clear(key)
    _, token = start_session(customer, user_agent)
    return customer, token


# --- add the missing contact ----------------------------------------------------------------


def add_contact(*, customer: Customer, kind: str, value: str) -> SentCode:
    """Send a code to a contact the account does not have yet. It is saved only when the code
    is verified."""
    user = customer.user
    if getattr(user, kind) is not None:
        raise ContactAlreadySet
    if User.objects.filter(**{kind: value}).exclude(pk=user.pk).exists():
        raise AccountExists
    issue_code(
        user=user,
        purpose=Purpose.CONTACT,
        channel=_channel(kind),
        identifier=value,
        locale=customer.locale,
    )
    return SentCode(identifier=value, channel=_channel(kind))


def verify_contact(*, customer: Customer, code: str) -> Customer:
    user = customer.user
    pending = latest_open_code(user, Purpose.CONTACT)
    if pending is None:
        raise NoPendingContact
    row = check_code(
        user=user,
        purpose=Purpose.CONTACT,
        identifier=pending.identifier,
        submitted=code,
    )
    kind = "email" if row.channel == Channel.EMAIL else "phone"
    try:
        with transaction.atomic():
            setattr(user, kind, row.identifier)
            user.save(update_fields=[kind, "updated_at"])
            _mark_verified(user, kind, timezone.now())
    except IntegrityError:
        # Someone else took the contact between the code and now.
        raise AccountExists from None
    return customer


# --- forgotten password ---------------------------------------------------------------------


def request_password_reset(*, kind: str, value: str) -> None:
    """Send a reset code to the verified contact. The limits and the answer are the same
    whether or not the account exists."""
    limits.cooldown(
        limits.key_for("reset-last", f"{kind}:{value}"), seconds=RESET_COOLDOWN_SECONDS
    )
    limits.hit(
        limits.key_for("reset-count", f"{kind}:{value}"),
        limit=RESET_PER_HOUR,
        window_seconds=60 * 60,
    )
    customer = customer_with(kind, value)
    if (
        customer is None
        or not contact_verified(customer.user, kind)
        or customer.is_blocked
        or not customer.user.is_active
    ):
        return
    issue_code(
        user=customer.user,
        purpose=Purpose.PASSWORD_RESET,
        channel=_channel(kind),
        identifier=value,
        locale=customer.locale,
        enforce_limits=False,
    )


def confirm_password_reset(
    *, kind: str, value: str, code: str, new_password: str
) -> None:
    limits.hit(
        limits.key_for("reset-confirm", f"{kind}:{value}"),
        limit=RESET_CONFIRM_ATTEMPTS,
        window_seconds=15 * 60,
    )
    customer = customer_with(kind, value)
    if customer is None:
        raise CodeInvalid
    user = customer.user
    row = check_code(
        user=user,
        purpose=Purpose.PASSWORD_RESET,
        identifier=value,
        submitted=code,
        consume=False,
    )
    # A weak password does not spend the code: the customer may try another.
    check_password_strength(new_password, user, "new_password")
    with transaction.atomic():
        mark_consumed(row)
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])
        revoke_all_sessions(customer)
