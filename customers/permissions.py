from typing import Any, cast

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from .models import Customer, CustomerSession


class IsCustomer(BasePermission):  # type: ignore[misc]
    """The request was authenticated with a customer token (so it has a customer profile)."""

    def has_permission(self, request: Request, view: Any) -> bool:
        return isinstance(request.auth, CustomerSession)


def get_customer(request: Request) -> Customer:
    """The customer behind a request that passed ``IsCustomer``."""
    return cast("CustomerSession", request.auth).customer
