"""``GET /orders/{id}``: a customer reads only their own order."""

import uuid

import pytest
from rest_framework.test import APIClient

from chat.tests.helpers import FULL_CAR, at_review, tap
from orders.models import Order

pytestmark = pytest.mark.django_db


def _placed(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    flow = at_review(monkeypatch)
    tap(flow.api, flow.cid, "confirm")
    return flow, Order.objects.get()


def _get(api: APIClient, order_id: object):  # type: ignore[no-untyped-def]
    return api.get(f"/api/v1/orders/{order_id}")


def test_a_customer_reads_their_placed_order(monkeypatch: pytest.MonkeyPatch) -> None:
    flow, order = _placed(monkeypatch)

    response = _get(flow.api, order.pk)

    assert response.status_code == 200
    assert response.json() == {
        "id": str(order.pk),
        "number": 1,
        "status": "placed",
        "order_type": "car",
        "placed_at": response.json()["placed_at"],
        "eta_minutes": None,
        "rejection_reason_code": None,
        "rejection_note": None,
        "subtotal_minor": 600,
        "total_minor": 600,
        "currency": "AED",
    }
    assert response["Cache-Control"] == "no-store"


def test_the_wait_the_restaurant_gave_is_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    flow, order = _placed(monkeypatch)
    Order.objects.filter(pk=order.pk).update(status="accepted", eta_minutes=10)

    body = _get(flow.api, order.pk).json()

    assert body["status"] == "accepted" and body["eta_minutes"] == 10
    assert body["rejection_reason_code"] is None


def test_a_rejection_shows_its_reason_and_note(monkeypatch: pytest.MonkeyPatch) -> None:
    flow, order = _placed(monkeypatch)
    Order.objects.filter(pk=order.pk).update(
        status="rejected", rejection_reason_code="other", rejection_note="Closing early"
    )

    body = _get(flow.api, order.pk).json()

    assert body["status"] == "rejected"
    assert body["rejection_reason_code"] == "other"
    assert body["rejection_note"] == "Closing early"


def test_a_rejection_without_a_note_has_a_null_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow, order = _placed(monkeypatch)
    Order.objects.filter(pk=order.pk).update(
        status="rejected", rejection_reason_code="too_busy"
    )

    body = _get(flow.api, order.pk).json()

    assert (
        body["rejection_reason_code"] == "too_busy" and body["rejection_note"] is None
    )


def test_another_customers_order_is_a_404(monkeypatch: pytest.MonkeyPatch) -> None:
    from chat.tests.helpers import signed_in

    _, order = _placed(monkeypatch)
    _, intruder = signed_in("intruder-order@example.com")

    response = _get(intruder, order.pk)

    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "not_found"


def test_an_unknown_order_is_a_404(monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _ = _placed(monkeypatch)

    assert _get(flow.api, uuid.uuid4()).status_code == 404


def test_a_customer_token_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    _, order = _placed(monkeypatch)

    assert _get(APIClient(), order.pk).status_code == 401


def test_the_order_never_shows_the_car_or_the_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow, order = _placed(monkeypatch)

    body = _get(flow.api, order.pk).content.decode()

    for private in ("A 12345", "Camry", "lift", "customer_lat", "vehicle"):
        assert private not in body
    assert FULL_CAR not in body
