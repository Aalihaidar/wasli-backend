"""Tenancy across every restaurant-owned table: restaurant A's rows are never returned for
restaurant B, a child row can never point at another restaurant's parent, and a new tenant
table cannot be added without being added to this isolation check."""

from collections.abc import Callable
from typing import Any

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import models

from chat.models import Conversation, Message, MessageKind, Sender
from chat.services import add_message
from chat.tests.factories import make_conversation
from core.tenancy import RestaurantOwnedModel
from customers.models import CustomerBlock
from customers.tests.factories import make_customer
from menu.models import MenuCategory, MenuItem, Option, OptionGroup
from menu.tests.factories import make_category, make_group, make_item, make_option
from orders.models import Order, OrderEvent, OrderItem
from orders.tests.factories import make_event, make_order, make_order_item
from restaurants.models import Restaurant, RestaurantMenuImage, StaffMembership
from restaurants.tests.factories import make_member, make_restaurant

pytestmark = pytest.mark.django_db

Builder = Callable[[Restaurant], models.Model]


def _menu_image(restaurant: Restaurant) -> models.Model:
    return RestaurantMenuImage.objects.create(restaurant=restaurant, image="m.jpg")


def _membership(restaurant: Restaurant) -> models.Model:
    return make_member(restaurant, f"staff-{restaurant.slug}")


def _category(restaurant: Restaurant) -> models.Model:
    return make_category(restaurant)


def _item(restaurant: Restaurant) -> models.Model:
    return make_item(make_category(restaurant))


def _group(restaurant: Restaurant) -> models.Model:
    return make_group(make_item(make_category(restaurant)))


def _option(restaurant: Restaurant) -> models.Model:
    return make_option(make_group(make_item(make_category(restaurant))))


def _conversation(restaurant: Restaurant) -> models.Model:
    return make_conversation(restaurant)


def _message(restaurant: Restaurant) -> models.Model:
    return add_message(make_conversation(restaurant), Sender.BOT, MessageKind.TEXT)


def _block(restaurant: Restaurant) -> models.Model:
    return CustomerBlock.objects.create(
        restaurant=restaurant, customer=make_customer(f"{restaurant.slug}@example.com")
    )


def _order(restaurant: Restaurant) -> models.Model:
    return make_order(restaurant)


def _order_item(restaurant: Restaurant) -> models.Model:
    return make_order_item(make_order(restaurant))


def _order_event(restaurant: Restaurant) -> models.Model:
    return make_event(make_order(restaurant))


# One builder per restaurant-owned table. test_every_tenant_table_is_covered fails when a new
# RestaurantOwnedModel is added without an entry here, so isolation is checked from day one.
BUILDERS: dict[type[models.Model], Builder] = {
    RestaurantMenuImage: _menu_image,
    StaffMembership: _membership,
    MenuCategory: _category,
    MenuItem: _item,
    OptionGroup: _group,
    Option: _option,
    Conversation: _conversation,
    Message: _message,
    CustomerBlock: _block,
    Order: _order,
    OrderItem: _order_item,
    OrderEvent: _order_event,
}


def _tenant_models() -> list[type[models.Model]]:
    return [
        model
        for model in apps.get_models()
        if issubclass(model, RestaurantOwnedModel) and not model._meta.abstract
    ]


def test_every_tenant_table_is_covered() -> None:
    assert set(_tenant_models()) == set(BUILDERS)


@pytest.mark.parametrize("model", _tenant_models(), ids=lambda m: m.__name__)
def test_the_restaurant_key_protects_the_rows(model: type[models.Model]) -> None:
    """A restaurant is deactivated, never deleted, so nothing it owns can disappear."""
    field = model._meta.get_field("restaurant")

    assert isinstance(field, models.ForeignKey)
    assert field.remote_field.on_delete is models.PROTECT
    assert not field.null


@pytest.mark.parametrize("model", list(BUILDERS), ids=lambda m: m.__name__)
def test_for_restaurant_returns_only_that_restaurants_rows(
    model: type[models.Model],
) -> None:
    a, b = make_restaurant("cafe-a"), make_restaurant("cafe-b")
    row_a, row_b = BUILDERS[model](a), BUILDERS[model](b)
    manager: Any = model._default_manager

    assert list(manager.for_restaurant(a)) == [row_a]
    assert list(manager.for_restaurant(b.pk)) == [row_b]
    assert row_a.pk not in {row.pk for row in manager.for_restaurant(b)}


class TestChildRowsCannotCrossRestaurants:
    """A child takes its parent's restaurant; one that names another restaurant is refused,
    so a row can never point at another restaurant's parent."""

    def setup_method(self) -> None:
        self.a = make_restaurant("cafe-a")
        self.b = make_restaurant("cafe-b")

    def test_an_item_under_another_restaurants_category_is_refused(self) -> None:
        category_b = make_category(self.b)

        with pytest.raises(ValidationError):
            MenuItem.objects.create(
                restaurant=self.a,
                category=category_b,
                name_en="Tea",
                name_ar="شاي",
                price_minor=500,
            )

    def test_an_option_group_under_another_restaurants_item_is_refused(self) -> None:
        item_b = make_item(make_category(self.b))

        with pytest.raises(ValidationError):
            OptionGroup.objects.create(
                restaurant=self.a, item=item_b, name_en="Size", name_ar="الحجم"
            )

    def test_an_option_in_another_restaurants_group_is_refused(self) -> None:
        group_b = make_group(make_item(make_category(self.b)))

        with pytest.raises(ValidationError):
            Option.objects.create(
                restaurant=self.a, group=group_b, name_en="Large", name_ar="كبير"
            )

    def test_a_message_in_another_restaurants_conversation_is_refused(self) -> None:
        conversation_b = make_conversation(self.b)

        with pytest.raises(ValidationError):
            Message.objects.create(
                restaurant=self.a,
                conversation=conversation_b,
                seq=1,
                sender=Sender.BOT,
            )

    def test_an_order_for_another_restaurants_conversation_is_refused(self) -> None:
        conversation_b = make_conversation(self.b)

        with pytest.raises(ValidationError):
            Order.objects.create(
                restaurant=self.a,
                customer=conversation_b.customer,
                conversation=conversation_b,
                number=1,
            )

    def test_an_order_item_under_another_restaurants_order_is_refused(self) -> None:
        order_b = make_order(self.b)

        with pytest.raises(ValidationError):
            make_order_item(order_b, restaurant=self.a)

    def test_an_order_event_under_another_restaurants_order_is_refused(self) -> None:
        order_b = make_order(self.b)

        with pytest.raises(ValidationError):
            make_event(order_b, restaurant=self.a)

    def test_a_child_without_a_restaurant_takes_its_parents(self) -> None:
        category_b = make_category(self.b)

        item = make_item(category_b)

        assert item.restaurant_id == self.b.pk


class TestBlocksAreForOneRestaurant:
    def test_a_block_at_one_restaurant_is_not_a_block_at_another(self) -> None:
        a, b = make_restaurant("cafe-a"), make_restaurant("cafe-b")
        customer = make_customer("sara@example.com")
        CustomerBlock.objects.create(restaurant=a, customer=customer)

        assert (
            CustomerBlock.objects.for_restaurant(a).filter(customer=customer).exists()
        )
        assert not (
            CustomerBlock.objects.for_restaurant(b).filter(customer=customer).exists()
        )
