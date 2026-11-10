"""Helpers for the customer-account tests: call the API the way the app does and read the code
from the outbox, the way the owner does on staging."""

import re
from typing import Any

import pytest
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from messaging.models import OutboxMessage

BASE = "/api/v1/customers"
SIGNUP = f"{BASE}/signup"
VERIFY = f"{BASE}/verify"
RESEND = f"{BASE}/resend-code"
LOGIN = f"{BASE}/login"
LOGOUT = f"{BASE}/logout"
ME = f"{BASE}/me"
CONTACT = f"{BASE}/me/contact"
CONTACT_VERIFY = f"{BASE}/me/contact/verify"
RESET = f"{BASE}/password-reset"
RESET_CONFIRM = f"{BASE}/password-reset/confirm"

PASSWORD = "correct-horse-battery-1"
NEW_PASSWORD = "another-long-passphrase-2"

EMAIL = "sara.example@example.com"
PHONE = "+971500000001"


def generous_throttles(monkeypatch: pytest.MonkeyPatch) -> None:
    """The scoped limits are for production; a test that signs up many times would meet them."""
    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        dict.fromkeys(
            (
                "customer_signup",
                "customer_verify",
                "customer_resend",
                "customer_login",
                "customer_contact",
                "customer_reset",
                "customer_reset_confirm",
            ),
            "10000/min",
        ),
    )


def customer_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Customer {token}"}


def sent_messages(recipient: str | None = None) -> list[OutboxMessage]:
    messages = OutboxMessage.objects.order_by("created_at")
    return list(messages.filter(recipient=recipient) if recipient else messages)


def last_code(recipient: str | None = None) -> str:
    """The six digits in the newest message (to ``recipient`` when given)."""
    messages = sent_messages(recipient)
    assert messages, "no message was sent"
    found = re.search(r"\b(\d{6})\b", messages[-1].body)
    assert found, "the message has no code"
    return found.group(1)


def sign_up(api: APIClient, **overrides: Any) -> Response:
    body: dict[str, Any] = {
        "full_name": "Sara Example",
        "email": EMAIL,
        "password": PASSWORD,
        "locale": "en",
        **overrides,
    }
    body = {key: value for key, value in body.items() if value is not None}
    return api.post(SIGNUP, body, format="json")


def verified_customer(
    api: APIClient, *, email: str = EMAIL, password: str = PASSWORD, **extra: Any
) -> tuple[str, dict[str, Any]]:
    """Sign up and verify through the API; returns the token and the profile."""
    assert sign_up(api, email=email, password=password, **extra).status_code == 201
    response = api.post(
        VERIFY, {"identifier": email, "code": last_code(email)}, format="json"
    )
    assert response.status_code == 200, response.content
    body = response.json()
    return body["token"], body["customer"]
