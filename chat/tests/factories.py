"""Small helpers that build valid chat rows for tests (invented data only)."""

from itertools import count

from chat.models import Conversation
from customers.models import Customer
from customers.tests.factories import make_customer
from restaurants.models import Restaurant
from restaurants.tests.factories import make_restaurant

_numbers = count(1)


def make_conversation(
    restaurant: Restaurant | None = None,
    customer: Customer | None = None,
    **extra: object,
) -> Conversation:
    """A conversation; a restaurant and a customer that nothing else uses are made when not
    given, so several calls in one test never clash on a slug or an email."""
    number = next(_numbers)
    return Conversation.objects.create(
        restaurant=restaurant or make_restaurant(f"cafe-{number}"),
        customer=customer or make_customer(f"sara-{number}@example.com"),
        **extra,
    )
