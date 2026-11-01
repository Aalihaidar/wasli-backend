import uuid
from typing import ClassVar

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """A person who signs in with email and password: restaurant staff or the platform owner.

    Customers are not users (they have their own model and an anonymous device token).
    A staff member's restaurant and role live in ``restaurants.StaffMembership``, not here,
    so one person can belong to several restaurants. Only the platform owner gets
    ``is_staff`` (access to the Django admin).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField("email address", unique=True)
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

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    def __str__(self) -> str:
        return self.email

    def clean(self) -> None:
        super().clean()
        # Runs before the uniqueness check in forms, so "A@x.com" and "a@x.com" collide there.
        self.email = self.email.strip().lower()

    def save(self, *args: object, **kwargs: object) -> None:
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    def get_full_name(self) -> str:
        return self.full_name or self.email

    def get_short_name(self) -> str:
        return self.full_name or self.email
