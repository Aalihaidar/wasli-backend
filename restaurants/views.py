from typing import Any

from django.conf import settings
from django.db.models import Prefetch, prefetch_related_objects
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from core.views import PublicAPIView
from menu.services import visible_categories
from restaurants.models import RestaurantMenuImage

from .serializers import (
    NearbyQuerySerializer,
    NearbyResponseSerializer,
    RestaurantDetailSerializer,
)
from .services import find_nearby, public_restaurants


class NearbyRestaurantsView(PublicAPIView):
    """Polling list: it keeps its own shape and is not paginated (docs/api-conventions.md)."""

    @extend_schema(
        operation_id="restaurants_nearby",
        tags=["restaurants"],
        summary="List the restaurants around a point",
        description=(
            "Visible restaurants (active, subscription not suspended) that serve the point, "
            "nearest first: the customer is within the platform search distance of the "
            "restaurant and, when the restaurant sets a service distance (`service_radius_m`), "
            "within that too. `distance_m` is the distance to the "
            "restaurant itself. When none is in range, `restaurants` is empty and `nearest` "
            "holds the closest active restaurant, so the app can say how far it is. "
            "`nearest` is absent when `restaurants` is not empty and when no restaurant is "
            "visible at all. This list is polled and is not paginated. No token is needed."
        ),
        parameters=[NearbyQuerySerializer],
        responses={200: NearbyResponseSerializer},
    )
    def get(self, request: Request) -> Response:
        query = NearbyQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = find_nearby(
            query.validated_data["lat"],
            query.validated_data["lng"],
            search_radius_m=settings.NEARBY_SEARCH_RADIUS_M,
            require_screen_online=settings.REQUIRE_SCREEN_ONLINE,
        )
        data: dict[str, Any] = {"restaurants": result.restaurants}
        if result.nearest is not None:
            data["nearest"] = result.nearest
        body = NearbyResponseSerializer(data, context={"request": request})
        return Response(body.data)


class RestaurantDetailView(PublicAPIView):
    @extend_schema(
        operation_id="restaurants_retrieve",
        tags=["restaurants"],
        summary="Read a restaurant and its menu",
        description=(
            "The restaurant's names, logo, brand colour, position and service distance, the "
            "menu images the chat sends, and the structured menu (categories, items, option "
            "groups and options with their availability) that the item picker uses. A "
            "restaurant that is not active or whose subscription is suspended is a `404`. No token is needed."
        ),
        responses={200: RestaurantDetailSerializer},
    )
    def get(self, request: Request, slug: str) -> Response:
        restaurant = get_object_or_404(
            public_restaurants().prefetch_related(
                Prefetch(
                    "restaurants_restaurantmenuimage_set",
                    queryset=RestaurantMenuImage.objects.all(),
                    to_attr="menu_images",
                ),
            ),
            slug=slug,
        )
        # The categories a customer sees (active, with every parent active), depth first.
        categories = visible_categories(restaurant)
        prefetch_related_objects(categories, "items__option_groups__options")
        restaurant.menu = categories  # type: ignore[attr-defined]
        return Response(
            RestaurantDetailSerializer(restaurant, context={"request": request}).data
        )
