"""Restaurant scoping: every restaurant-owned row carries a ``restaurant`` and every query
that serves a restaurant's staff or a customer of that restaurant goes through it.

``Model.objects.for_restaurant(restaurant)`` is the only way a view should reach tenant rows,
so one restaurant can never read or change another's data. Each endpoint also gets a test.
"""

import uuid
from typing import Self, TypeVar

from django.core.exceptions import ValidationError
from django.db import models

from core.models import BaseModel

_T = TypeVar("_T", bound=models.Model, covariant=True)


class RestaurantScopedQuerySet(models.QuerySet[_T]):
    def for_restaurant(self, restaurant: models.Model | uuid.UUID | str) -> Self:
        """Rows of one restaurant, given the restaurant or its id."""
        restaurant_id = (
            restaurant.pk if isinstance(restaurant, models.Model) else restaurant
        )
        return self.filter(restaurant_id=restaurant_id)


class RestaurantScopedManager(models.Manager[_T]):
    def get_queryset(self) -> RestaurantScopedQuerySet[_T]:
        return RestaurantScopedQuerySet(self.model, using=self._db)

    def for_restaurant(
        self, restaurant: models.Model | uuid.UUID | str
    ) -> RestaurantScopedQuerySet[_T]:
        return self.get_queryset().for_restaurant(restaurant)


class RestaurantOwnedModel(BaseModel):
    """Abstract base for a table whose rows belong to one restaurant.

    The foreign key is ``PROTECT``: a restaurant is deactivated, never deleted, so nothing
    that belongs to it (and nothing an order refers to) disappears with it.
    """

    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_set",
    )

    objects = RestaurantScopedManager()

    class Meta:
        abstract = True


def align_with_parent(
    obj: RestaurantOwnedModel, parent: RestaurantOwnedModel | None, field: str
) -> None:
    """Make a child row belong to its parent's restaurant.

    A child (a menu item under a category, an option under a group) takes the restaurant of
    its parent when none is set, and is refused when it names a different one, so a row
    can never point at another restaurant's parent.
    """
    if parent is None:
        return
    if obj.restaurant_id is None:
        obj.restaurant_id = parent.restaurant_id
    elif obj.restaurant_id != parent.restaurant_id:
        raise ValidationError({field: "This belongs to a different restaurant."})
