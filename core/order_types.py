"""The kinds of order. The first version only takes car orders; the other two values exist so the
contract and the database do not change when dine-in and delivery arrive (ADR 0017)."""

from django.db import models


class OrderType(models.TextChoices):
    CAR = "car", "To the car"
    DINE_IN = "dine_in", "Dine in"
    DELIVERY = "delivery", "Delivery"


# What the API accepts today: any other value is refused with ``unsupported_order_type``.
SUPPORTED_ORDER_TYPES = frozenset({OrderType.CAR.value})
