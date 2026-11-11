from typing import Any, ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.locales import LOCALE_CHOICES, Locale
from core.models import BaseModel
from core.tenancy import RestaurantOwnedModel
from messaging.models import Channel


class Customer(BaseModel):
    """The profile of a person who orders from their car.

    Every customer has a ``User`` (they sign up and sign in), but a user is either a customer
    or restaurant staff or the platform team, never two of them: a customer's user is never
    ``is_staff`` or a superuser and never holds a restaurant membership. Staff endpoints
    require a membership, customer endpoints require this profile.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="customer"
    )
    display_name = models.CharField(max_length=150, blank=True)
    locale = models.CharField(
        max_length=2, choices=LOCALE_CHOICES, default=Locale.EN.value
    )
    # The platform-wide ban. Per-restaurant blocks are ``CustomerBlock`` rows.
    is_blocked = models.BooleanField(default=False)
    last_seen_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.display_name or str(self.user)

    def clean(self) -> None:
        super().clean()
        self._check_rules()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self._check_rules()
        super().save(*args, **kwargs)

    def _check_rules(self) -> None:
        if self.user_id is None:
            return
        user = self.user
        if user.is_staff or user.is_superuser:
            raise ValidationError(
                {"user": "A customer cannot be a member of the platform team."}
            )
        # Imported here: customers and restaurants both point at each other's data.
        from restaurants.models import StaffMembership

        if StaffMembership.objects.filter(user_id=self.user_id).exists():
            raise ValidationError(
                {"user": "A restaurant staff account cannot also be a customer."}
            )


class CustomerSession(BaseModel):
    """A signed-in device of a customer. Only the SHA-256 hash of the token is stored; the
    token itself is shown once, when the session is started."""

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="sessions"
    )
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    user_agent = models.CharField(max_length=255, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.customer} ({self.created_at:%Y-%m-%d})"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class Vehicle(BaseModel):
    """A car a customer has ordered from. Saved when an order is placed, so the next
    conversation can offer it. An order keeps its own copy of these details."""

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="vehicles"
    )
    plate = models.CharField(max_length=20)
    colour = models.CharField(max_length=30, blank=True)
    make_model = models.CharField(max_length=60, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-last_used_at", "plate")
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["customer", "plate"], name="unique_plate_per_customer"
            )
        ]

    def __str__(self) -> str:
        return self.plate


class CustomerBlock(RestaurantOwnedModel):
    """A restaurant refuses orders from one customer."""

    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="blocks"
    )
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["restaurant", "customer"], name="unique_block_per_restaurant"
            )
        ]

    def __str__(self) -> str:
        return f"{self.restaurant} blocks {self.customer}"


class VerificationCode(BaseModel):
    """A six-digit code sent to an email address or a phone number.

    Only a keyed hash of the code is stored (``customers.verification.hash_code``): the plain
    code exists in the message that was sent and nowhere else. A code is valid until
    ``expires_at``, for a limited number of wrong attempts, and until a newer code for the same
    purpose replaces it (``invalidated_at``) or it is used (``consumed_at``).
    """

    class Purpose(models.TextChoices):
        SIGNUP = "signup", "Verify the contact given at sign-up"
        CONTACT = "contact", "Verify a contact added later"
        PASSWORD_RESET = "password_reset", "Reset the password"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="verification_codes",
    )
    purpose = models.CharField(max_length=20, choices=Purpose)
    channel = models.CharField(max_length=5, choices=Channel)
    # The email address or phone number the code was sent to, normalised. For ``contact`` it is
    # the new contact, which is saved on the user only after the code is verified.
    identifier = models.CharField(max_length=254)
    code_hash = models.CharField(max_length=64, editable=False)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes: ClassVar[list[models.Index]] = [
            # Resend limits count the codes sent to one contact for one purpose.
            models.Index(
                fields=["identifier", "purpose", "created_at"],
                name="verification_contact_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.purpose} code for {self.user_id}"

    @property
    def is_open(self) -> bool:
        """Not used and not replaced (it may still have expired)."""
        return self.consumed_at is None and self.invalidated_at is None
