import uuid
from typing import ClassVar

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.db.models import Q

from .identifiers import (
    normalize_email,
    normalize_phone,
    normalize_username,
    validate_phone,
    validate_username,
)
from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """The one account table: platform team, restaurant staff and registered customers.

    A person signs in with a username, an email address or a phone number plus a password.
    Each identifier is optional, unique when set and stored as NULL when empty (never as an
    empty string); at least one is required. Restaurant accounts always use a username (the
    ``restaurants.StaffMembership`` rule); the platform team signs in with email.

    A staff member's restaurant and role live in ``restaurants.StaffMembership``, not here,
    so one person can belong to several restaurants. Only the platform team gets
    ``is_staff`` (access to the Django admin). Demo customers are anonymous and have no user.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # null=True on these text fields is deliberate: an empty identifier must be NULL so
    # that several accounts can leave it unset under a unique constraint.
    username = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
        validators=[validate_username],
        help_text=(
            "3 to 30 characters: letters, digits, dots, underscores and hyphens, "
            "starting with a letter. Stored in lowercase."
        ),
    )
    email = models.EmailField("email address", unique=True, null=True, blank=True)
    phone = models.CharField(
        max_length=32,
        unique=True,
        null=True,
        blank=True,
        validators=[validate_phone],
        help_text=(
            "International format, for example +971501234567. "
            "Numbers without a country code are read as UAE numbers."
        ),
    )
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    must_change_password = models.BooleanField(
        default=False,
        help_text="Set for a new member with a temporary password.",
    )
    full_name = models.CharField(max_length=150, blank=True)
    # Deactivate instead of delete: orders keep pointing at the staff member who handled them.
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(
        "staff status",
        default=False,
        help_text="Designates whether the user can sign in to the Django admin.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "username"
    # Asked by ``createsuperuser`` in addition to the username: the platform team signs in
    # with email.
    REQUIRED_FIELDS: ClassVar[list[str]] = ["email"]

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=(
                    Q(username__isnull=False)
                    | Q(email__isnull=False)
                    | Q(phone__isnull=False)
                ),
                name="user_has_an_identifier",
                violation_error_message="Set a username, an email address or a phone number.",
            ),
            models.CheckConstraint(
                condition=~Q(username="") & ~Q(email="") & ~Q(phone=""),
                name="user_identifiers_not_empty",
                violation_error_message="An identifier cannot be an empty string.",
            ),
        ]

    def __str__(self) -> str:
        return self.username or self.email or self.phone or str(self.pk)

    def normalize_identifiers(self) -> None:
        """Lowercase, trim and convert blanks to None; phone to international format."""
        self.username = normalize_username(self.username)
        self.email = normalize_email(self.email)
        self.phone = normalize_phone(self.phone)

    def clean(self) -> None:
        super().clean()
        # Runs before the uniqueness check in forms, so "A@x.com" and "a@x.com" collide there.
        self.normalize_identifiers()

    def save(self, *args: object, **kwargs: object) -> None:
        self.normalize_identifiers()
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    def get_full_name(self) -> str:
        return self.full_name or str(self)

    def get_short_name(self) -> str:
        return self.full_name or str(self)
