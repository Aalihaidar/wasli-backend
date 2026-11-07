from typing import TYPE_CHECKING, Any

from django.contrib.auth.base_user import BaseUserManager

from .identifiers import identify, normalize_username

if TYPE_CHECKING:
    from .models import User


class UserManager(BaseUserManager["User"]):
    """Creates users that sign in with a username, an email address or a phone number."""

    use_in_migrations = True

    def _create_user(
        self,
        username: str | None,
        email: str | None,
        phone: str | None,
        password: str | None,
        **extra_fields: Any,
    ) -> User:
        user = self.model(username=username, email=email, phone=phone, **extra_fields)
        user.normalize_identifiers()
        # A password of None stores an unusable password (for example an account whose password is set later).
        user.set_password(password)
        # Rejects a bad identifier format, a duplicate, or a user without any identifier.
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(
        self,
        username: str | None = None,
        password: str | None = None,
        *,
        email: str | None = None,
        phone: str | None = None,
        **extra_fields: Any,
    ) -> User:
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(username, email, phone, password, **extra_fields)

    def create_superuser(
        self,
        username: str | None = None,
        password: str | None = None,
        *,
        email: str | None = None,
        phone: str | None = None,
        **extra_fields: Any,
    ) -> User:
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields["is_staff"] is not True:
            raise ValueError("A superuser must have is_staff=True.")
        if extra_fields["is_superuser"] is not True:
            raise ValueError("A superuser must have is_superuser=True.")
        # The platform team signs in with email.
        if not (email or "").strip():
            raise ValueError("A superuser must have an email address.")
        return self._create_user(username, email, phone, password, **extra_fields)

    def get_by_natural_key(self, username: str | None) -> User:
        # ``createsuperuser`` looks the new account up by USERNAME_FIELD; stored usernames
        # are lowercase.
        return self.get(username=normalize_username(username))

    def get_by_identifier(self, value: str) -> User | None:
        """Find the account whose email, phone or username equals ``value``."""
        found = identify(value)
        if found is None:
            return None
        field, normalized = found
        return self.filter(**{field: normalized}).first()
