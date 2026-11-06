from typing import Any

from django.contrib.auth.backends import ModelBackend
from django.http import HttpRequest

from .models import User


class IdentifierBackend(ModelBackend):
    """Signs a user in with one value (email, phone or username) plus the password.

    The Django admin and ``POST /auth/login`` pass that single value as ``username``.
    Permission checks are inherited from ``ModelBackend``.
    """

    def authenticate(
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> User | None:
        if username is None or password is None:
            return None
        user = User.objects.get_by_identifier(username)
        if user is None:
            # Run the hasher once so an unknown account takes as long as a wrong password.
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
