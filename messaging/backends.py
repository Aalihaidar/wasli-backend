"""Delivery backends: how one outgoing email or SMS leaves the system.

Nothing else in the project sends a message: a view or a service calls
``messaging.services.send_message`` and the backend named by ``MESSAGING_BACKEND`` does the
work. Production backends (Resend for email, an SMS provider) are added here later.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from .models import OutboxMessage


@dataclass(frozen=True)
class OutgoingMessage:
    """What a caller hands to the delivery interface."""

    channel: str
    recipient: str
    body: str
    purpose: str
    subject: str = ""


class MessagingBackend(ABC):
    @abstractmethod
    def send(self, message: OutgoingMessage) -> None:
        """Deliver one message, or raise when it cannot be delivered."""


def purge_old_messages(now: datetime | None = None) -> int:
    """Delete outbox messages older than ``OUTBOX_RETENTION_HOURS``; returns how many.

    The stored bodies hold plain verification codes, so they are not kept: the owner reads a
    code within minutes of asking for it.
    """
    cutoff = (now or timezone.now()) - timedelta(hours=settings.OUTBOX_RETENTION_HOURS)
    deleted, _ = OutboxMessage.objects.filter(created_at__lt=cutoff).delete()
    return deleted


class DisabledBackend(MessagingBackend):
    """Sends nothing: every send fails loudly. Production uses it until a real backend
    (Resend for email, an SMS provider) exists, so no code is ever lost silently."""

    def send(self, message: OutgoingMessage) -> None:
        raise ImproperlyConfigured(
            "Messaging is disabled (MESSAGING_BACKEND=disabled): no email or SMS can be sent."
        )


class OutboxBackend(MessagingBackend):
    """Stores the message in the database so the owner reads it in the Django admin.

    The stored body holds the plain verification code, so this backend never runs in
    production: it refuses to be created when ``ENVIRONMENT`` is ``production``.
    """

    def __init__(self) -> None:
        if settings.ENVIRONMENT == "production":
            raise ImproperlyConfigured(
                "The outbox messaging backend stores codes in plain text and cannot be "
                "used when ENVIRONMENT=production. Set MESSAGING_BACKEND to a real backend."
            )

    def send(self, message: OutgoingMessage) -> None:
        row = OutboxMessage(
            channel=message.channel,
            recipient=message.recipient,
            subject=message.subject,
            body=message.body,
            purpose=message.purpose,
        )
        row.full_clean()
        row.save()
        # No scheduler runs on the free staging service, so each send tidies the table.
        purge_old_messages()


BACKENDS: dict[str, type[MessagingBackend]] = {
    "outbox": OutboxBackend,
    "disabled": DisabledBackend,
}


def get_backend() -> MessagingBackend:
    """The backend chosen by ``MESSAGING_BACKEND``."""
    try:
        backend_class = BACKENDS[settings.MESSAGING_BACKEND]
    except KeyError:
        raise ImproperlyConfigured(
            f"Unknown MESSAGING_BACKEND {settings.MESSAGING_BACKEND!r}."
        ) from None
    return backend_class()
