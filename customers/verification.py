"""The life of a verification code: issue it, send it, check it, spend it.

* A code is six digits, valid 10 minutes, with 5 wrong attempts. Only a keyed hash is stored.
* A new code for the same purpose replaces the open one.
* A contact gets a new code at most every 60 seconds and at most 5 an hour (per purpose).
"""

import hashlib
import hmac
import math
import secrets
from datetime import datetime, timedelta
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import Throttled

from messaging.models import Channel
from messaging.models import Purpose as MessagePurpose
from messaging.services import send_message
from users.models import User

from .errors import CodeExpired, CodeInvalid, TooManyAttempts
from .models import VerificationCode
from .texts import code_message

CODE_LENGTH = 6
CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
RESEND_WAIT = timedelta(seconds=60)
SEND_WINDOW = timedelta(hours=1)
MAX_SENDS_PER_WINDOW = 5

Purpose = VerificationCode.Purpose


def generate_code() -> str:
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def hash_code(code_id: UUID, code: str) -> str:
    """A keyed hash of the code. Six digits would fall to a plain hash in a second; the secret
    key and the row's own id make a stolen table useless without the key."""
    return hmac.new(
        settings.SECRET_KEY.encode(), f"{code_id}:{code}".encode(), hashlib.sha256
    ).hexdigest()


def enforce_send_limits(identifier: str, purpose: str, now: datetime) -> None:
    """Refuse a new code that comes too soon or too often, with the seconds to wait."""
    recent = VerificationCode.objects.filter(
        identifier=identifier, purpose=purpose, created_at__gt=now - SEND_WINDOW
    ).order_by("-created_at")
    newest = recent.first()
    if newest is not None and now - newest.created_at < RESEND_WAIT:
        wait = RESEND_WAIT - (now - newest.created_at)
        raise Throttled(wait=math.ceil(wait.total_seconds()))
    window = list(recent[:MAX_SENDS_PER_WINDOW])
    if len(window) >= MAX_SENDS_PER_WINDOW:
        # A slot opens when the oldest code of the window leaves it.
        wait = window[-1].created_at + SEND_WINDOW - now
        raise Throttled(wait=max(1, math.ceil(wait.total_seconds())))


def issue_code(
    *,
    user: User,
    purpose: str,
    channel: str,
    identifier: str,
    locale: str,
    enforce_limits: bool = True,
    now: datetime | None = None,
) -> VerificationCode:
    """Create a code, replace the open one and send it, all or nothing: if the message cannot be
    sent, nothing is saved."""
    now = now or timezone.now()
    with transaction.atomic():
        if enforce_limits:
            enforce_send_limits(identifier, purpose, now)
        VerificationCode.objects.filter(
            user=user,
            purpose=purpose,
            consumed_at__isnull=True,
            invalidated_at__isnull=True,
        ).update(invalidated_at=now)
        code = generate_code()
        row = VerificationCode(
            user=user,
            purpose=purpose,
            channel=channel,
            identifier=identifier,
            expires_at=now + CODE_TTL,
        )
        row.code_hash = hash_code(row.pk, code)
        row.save()
        subject, body = code_message(
            purpose, locale, code, int(CODE_TTL.total_seconds() // 60)
        )
        send_message(
            Channel(channel),
            identifier,
            body,
            MessagePurpose.PASSWORD_RESET
            if purpose == Purpose.PASSWORD_RESET
            else MessagePurpose.VERIFICATION,
            subject=subject if channel == Channel.EMAIL else "",
        )
    return row


def latest_open_code(
    user: User, purpose: str, identifier: str | None = None
) -> VerificationCode | None:
    rows = VerificationCode.objects.filter(
        user=user,
        purpose=purpose,
        consumed_at__isnull=True,
        invalidated_at__isnull=True,
    )
    if identifier is not None:
        rows = rows.filter(identifier=identifier)
    return rows.order_by("-created_at").first()


def check_code(
    *,
    user: User,
    purpose: str,
    identifier: str | None,
    submitted: str,
    consume: bool = True,
    now: datetime | None = None,
) -> VerificationCode:
    """Check ``submitted`` against the open code. Raises ``CodeInvalid``, ``CodeExpired`` or
    ``TooManyAttempts``; a wrong code counts as an attempt, and the count survives the error."""
    now = now or timezone.now()
    failure: Exception | None = None
    with transaction.atomic():
        row = (
            VerificationCode.objects.select_for_update()
            .filter(
                user=user,
                purpose=purpose,
                consumed_at__isnull=True,
                invalidated_at__isnull=True,
                **({} if identifier is None else {"identifier": identifier}),
            )
            .order_by("-created_at")
            .first()
        )
        if row is None:
            failure = CodeInvalid()
        elif row.expires_at <= now:
            failure = CodeExpired()
        elif row.attempts >= MAX_ATTEMPTS:
            failure = TooManyAttempts()
        elif not hmac.compare_digest(row.code_hash, hash_code(row.pk, submitted)):
            row.attempts += 1
            row.save(update_fields=["attempts", "updated_at"])
            failure = CodeInvalid()
        elif consume:
            row.consumed_at = now
            row.save(update_fields=["consumed_at", "updated_at"])
    # Raised after the block, so the attempt that was just counted is not rolled back.
    if failure is not None:
        raise failure
    assert row is not None  # noqa: S101
    return row


def mark_consumed(row: VerificationCode, now: datetime | None = None) -> None:
    row.consumed_at = now or timezone.now()
    row.save(update_fields=["consumed_at", "updated_at"])
