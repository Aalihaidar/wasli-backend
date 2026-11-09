from typing import ClassVar

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models

from core.models import BaseModel
from users.identifiers import normalize_email, normalize_phone


class Channel(models.TextChoices):
    EMAIL = "email", "Email"
    SMS = "sms", "SMS"


class Purpose(models.TextChoices):
    VERIFICATION = "verification", "Verification code"
    PASSWORD_RESET = "password_reset", "Password reset"


class OutboxMessage(BaseModel):
    """An email or an SMS that the outbox backend stored instead of sending.

    Used on local and staging only, so the owner can read a verification code in the Django
    admin. The body holds the plain code, which is why the outbox backend refuses to run in
    production (``messaging/backends.py``). Nothing here is ever written to a log.
    """

    channel = models.CharField(max_length=5, choices=Channel)
    recipient = models.CharField(max_length=254)
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    purpose = models.CharField(max_length=20, choices=Purpose)

    class Meta:
        ordering = ("-created_at",)
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["channel", "recipient"], name="outbox_recipient_idx")
        ]

    def __str__(self) -> str:
        return f"{self.channel} to {self.recipient}: {self.purpose}"

    def clean(self) -> None:
        super().clean()
        self._normalise()

    def save(self, *args: object, **kwargs: object) -> None:
        self._normalise()
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    def _normalise(self) -> None:
        """An email goes to a valid lower-case address, an SMS to a valid number in international
        format."""
        if self.channel == Channel.EMAIL:
            address = normalize_email(self.recipient) or ""
            validate_email(address)
            self.recipient = address
        elif self.channel == Channel.SMS:
            number = normalize_phone(self.recipient)
            if number is None:
                raise ValidationError({"recipient": "A phone number is required."})
            self.recipient = number
