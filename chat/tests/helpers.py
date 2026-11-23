"""Helpers for the chat tests: a small menu, a signed-in customer and a scripted assistant.

Invented data only. The assistant is always the fake adapter: ``scripted`` puts it in place of
the real one and the test says what it understood.
"""

import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from rest_framework.response import Response
from rest_framework.test import APIClient

from assistant.adapters.fake import FakeAdapter
from assistant.errors import AssistantError
from assistant.services import Assistant
from assistant.types import (
    ActionType,
    Language,
    OrderAction,
    OrderIntent,
    OrderQuestion,
    ParseOrderResult,
    QuestionKind,
)
from customers.models import Customer
from customers.services import start_session
from customers.tests.factories import make_customer
from menu.models import MenuCategory, MenuItem, Option, OptionGroup
from menu.tests.factories import (
    make_category,
    make_group,
    make_item,
    make_option,
)
from restaurants.models import Restaurant
from restaurants.tests.factories import make_restaurant


@dataclass
class World:
    restaurant: Restaurant
    drinks: MenuCategory
    karak: MenuItem
    sandwich: MenuItem
    chicken: MenuItem
    beef: MenuItem
    latte: MenuItem
    finished: MenuItem
    milk: OptionGroup
    oat: Option
    whole: Option


def make_world(slug: str = "cafe-one", **restaurant_extra: object) -> World:
    """A restaurant with a menu that covers every case the engine handles."""
    restaurant = make_restaurant(slug, **restaurant_extra)
    drinks = make_category(restaurant, "Drinks")
    latte = make_item(drinks, "Latte", 1000)
    milk = make_group(latte, "Milk", min_select=1, max_select=1)
    return World(
        restaurant=restaurant,
        drinks=drinks,
        karak=make_item(drinks, "Karak tea", 300),
        sandwich=make_item(drinks, "Cheese sandwich", 1200),
        chicken=make_item(drinks, "Chicken burger", 2500),
        beef=make_item(drinks, "Beef burger", 2800),
        latte=latte,
        finished=make_item(drinks, "Iced tea", 500, is_available=False),
        milk=milk,
        oat=make_option(milk, "Oat", 200),
        whole=make_option(milk, "Whole", 0),
    )


def signed_in(email: str = "sara-chat@example.com") -> tuple[Customer, APIClient]:
    """A verified customer and an API client that sends their token."""
    customer = make_customer(email)
    _, token = start_session(customer)
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Customer {token}")
    return customer, api


def scripted(
    monkeypatch: pytest.MonkeyPatch,
    script: dict[tuple[str, str], Any] | None = None,
    *,
    fail_with: AssistantError | None = None,
) -> FakeAdapter:
    """Put a fake assistant that knows ``script`` in place of the real one."""
    adapter = FakeAdapter(script, fail_with=fail_with)
    monkeypatch.setattr("chat.engine.get_assistant", lambda: Assistant(adapter))
    return adapter


def add(
    item: MenuItem, quantity: int = 1, options: tuple[Option, ...] = ()
) -> OrderAction:
    return OrderAction(
        type=ActionType.ADD,
        item_id=str(item.pk),
        quantity=quantity,
        option_ids=[str(option.pk) for option in options],
    )


def understood(
    *actions: OrderAction,
    unmatched: tuple[str, ...] = (),
    questions: tuple[OrderQuestion, ...] = (),
    intent: OrderIntent = OrderIntent.ORDER_CHANGE,
) -> ParseOrderResult:
    return ParseOrderResult(
        language=Language.EN,
        intent=intent,
        actions=list(actions),
        unmatched=list(unmatched),
        questions=list(questions),
    )


def which_burger(world: World) -> OrderQuestion:
    return OrderQuestion(
        kind=QuestionKind.CHOOSE_ITEM,
        mention="burger",
        item_ids=[str(world.chicken.pk), str(world.beef.pk)],
    )


def parse(text: str) -> tuple[str, str]:
    """The key of a scripted ``parse_order`` answer."""
    return ("parse_order", text)


def open_chat(api: APIClient, slug: str = "cafe-one", **body: object) -> Response:
    return api.post(f"/api/v1/restaurants/{slug}/conversations", body, format="json")


def say_text(
    api: APIClient,
    conversation_id: str,
    text: str,
    client_message_id: uuid.UUID | None = None,
) -> Response:
    return api.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        {"client_message_id": str(client_message_id or uuid.uuid4()), "text": text},
        format="json",
    )


def tap(
    api: APIClient,
    conversation_id: str,
    action: str,
    client_message_id: uuid.UUID | None = None,
    **extra: object,
) -> Response:
    return api.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        {
            "client_message_id": str(client_message_id or uuid.uuid4()),
            "action": action,
            **extra,
        },
        format="json",
    )


def bot_texts(response: Response) -> list[str]:
    return [m["text"] for m in response.json()["messages"] if m["sender"] == "bot"]


def summary_of(response: Response) -> dict[str, Any]:
    """The ``summary`` of the order summary message in a response."""
    found = [m for m in response.json()["messages"] if m["kind"] == "order_summary"]
    assert found, response.json()
    summary: dict[str, Any] = found[-1]["payload"]["summary"]
    return summary
