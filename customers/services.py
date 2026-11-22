import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .errors import PhoneNotVerified
from .models import Customer, CustomerSession

# A session's "last seen" is refreshed at most this often, so a busy client (polling every
# few seconds) does not write to the database on every request.
TOUCH_INTERVAL = timedelta(seconds=60)


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(
    customer: Customer, user_agent: str = ""
) -> tuple[CustomerSession, str]:
    """Open a session and return it with the token. The token is not stored anywhere: the
    caller hands it to the client once."""
    token = generate_token()
    session = CustomerSession.objects.create(
        customer=customer,
        token_hash=hash_token(token),
        user_agent=user_agent[:255],
        last_seen_at=timezone.now(),
    )
    return session, token


def get_active_session(token: str) -> CustomerSession | None:
    """The session a token belongs to, unless it was revoked."""
    return (
        CustomerSession.objects.select_related("customer__user")
        .filter(token_hash=hash_token(token), revoked_at__isnull=True)
        .first()
    )


def revoke_session(session: CustomerSession) -> None:
    if session.revoked_at is None:
        session.revoked_at = timezone.now()
        session.save(update_fields=["revoked_at", "updated_at"])


def revoke_all_sessions(customer: Customer) -> int:
    """Sign a customer out everywhere (for example after a password reset)."""
    now = timezone.now()
    return CustomerSession.objects.filter(
        customer=customer, revoked_at__isnull=True
    ).update(revoked_at=now, updated_at=now)


def touch_session(session: CustomerSession) -> None:
    now = timezone.now()
    if session.last_seen_at and now - session.last_seen_at < TOUCH_INTERVAL:
        return
    session.last_seen_at = now
    CustomerSession.objects.filter(pk=session.pk).update(
        last_seen_at=now, updated_at=now
    )
    Customer.objects.filter(pk=session.customer_id).update(
        last_seen_at=now, updated_at=now
    )


def ensure_phone_verified_for_order(customer: Customer) -> None:
    """Refuse the final confirmation of an order when the phone check is on and the customer's
    phone is not verified. It changes nothing and stores nothing, so the same request goes
    through once the customer has verified a phone (``POST /customers/me/contact`` and
    ``/me/contact/verify``). Off by default: ``REQUIRE_VERIFIED_PHONE`` comes on with the pilot."""
    if settings.REQUIRE_VERIFIED_PHONE and customer.user.phone_verified_at is None:
        raise PhoneNotVerified
