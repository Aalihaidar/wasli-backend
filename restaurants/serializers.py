"""The public shapes of a restaurant: the nearby list and the detail with its menu.

Image fields return absolute URLs (the request is in the serializer context) or ``null``.
Prices are integers in fils (``*_minor``); the API never sends formatted prices.
"""

from rest_framework import serializers

from core.geo import is_valid_location
from menu.models import MenuCategory, MenuItem, Option, OptionGroup

from .models import ParkingLot, Restaurant, RestaurantMenuImage


class NearbyQuerySerializer(serializers.Serializer):  # type: ignore[misc]
    lat = serializers.FloatField(help_text="Latitude of the customer, in degrees.")
    lng = serializers.FloatField(help_text="Longitude of the customer, in degrees.")

    def validate(self, attrs: dict[str, float]) -> dict[str, float]:
        if not is_valid_location(attrs["lat"], attrs["lng"]):
            raise serializers.ValidationError(
                {"lat": "Latitude or longitude is out of range."},
                code="invalid_location",
            )
        return attrs


class ParkingLotSerializer(serializers.ModelSerializer):  # type: ignore[misc]
    class Meta:
        model = ParkingLot
        fields = ("name", "latitude", "longitude", "radius_m")
        read_only_fields = fields


class NearbyRestaurantSerializer(serializers.Serializer):  # type: ignore[misc]
    slug = serializers.CharField(source="restaurant.slug")
    name_en = serializers.CharField(source="restaurant.name_en")
    name_ar = serializers.CharField(source="restaurant.name_ar")
    logo_url = serializers.ImageField(
        source="restaurant.logo", read_only=True, allow_null=True
    )
    latitude = serializers.FloatField(source="restaurant.latitude")
    longitude = serializers.FloatField(source="restaurant.longitude")
    distance_m = serializers.IntegerField(
        help_text="Metres from the customer to the restaurant."
    )
    is_open = serializers.BooleanField(
        help_text="True while the restaurant's site is online and can take an order."
    )


class NearestRestaurantSerializer(NearbyRestaurantSerializer):
    parking_lot = ParkingLotSerializer(source="restaurant.parking_lot", read_only=True)


class NearbyResponseSerializer(serializers.Serializer):  # type: ignore[misc]
    restaurants = NearbyRestaurantSerializer(many=True)
    nearest = NearestRestaurantSerializer(
        allow_null=True,
        help_text=(
            "Only when `restaurants` is empty: the closest active restaurant, so the "
            "app can say how far it is. `null` otherwise."
        ),
    )


class MenuImageSerializer(serializers.ModelSerializer):  # type: ignore[misc]
    image_url = serializers.ImageField(source="image", read_only=True)

    class Meta:
        model = RestaurantMenuImage
        fields = ("image_url", "caption_en", "caption_ar")
        read_only_fields = fields


class OptionSerializer(serializers.ModelSerializer):  # type: ignore[misc]
    class Meta:
        model = Option
        fields = (
            "id",
            "name_en",
            "name_ar",
            "price_delta_minor",
            "is_available",
            "is_default",
        )
        read_only_fields = fields


class OptionGroupSerializer(serializers.ModelSerializer):  # type: ignore[misc]
    options = OptionSerializer(many=True, read_only=True)

    class Meta:
        model = OptionGroup
        fields = ("id", "name_en", "name_ar", "min_select", "max_select", "options")
        read_only_fields = fields


class MenuItemSerializer(serializers.ModelSerializer):  # type: ignore[misc]
    image_url = serializers.ImageField(source="image", read_only=True, allow_null=True)
    option_groups = OptionGroupSerializer(many=True, read_only=True)

    class Meta:
        model = MenuItem
        fields = (
            "id",
            "name_en",
            "name_ar",
            "description_en",
            "description_ar",
            "price_minor",
            "image_url",
            "is_available",
            "option_groups",
        )
        read_only_fields = fields


class MenuCategorySerializer(serializers.ModelSerializer):  # type: ignore[misc]
    items = MenuItemSerializer(many=True, read_only=True)

    class Meta:
        model = MenuCategory
        fields = ("id", "name_en", "name_ar", "items")
        read_only_fields = fields


class RestaurantDetailSerializer(serializers.ModelSerializer):  # type: ignore[misc]
    logo_url = serializers.ImageField(source="logo", read_only=True, allow_null=True)
    brand_colour = serializers.CharField(
        help_text="A hex colour such as `#1A73E8`, or empty when none is set."
    )
    parking_lot = ParkingLotSerializer(read_only=True)
    menu_images = MenuImageSerializer(many=True, read_only=True)
    menu = MenuCategorySerializer(many=True, read_only=True)

    class Meta:
        model = Restaurant
        fields = (
            "slug",
            "name_en",
            "name_ar",
            "logo_url",
            "brand_colour",
            "latitude",
            "longitude",
            "currency",
            "parking_lot",
            "menu_images",
            "menu",
        )
        read_only_fields = fields
