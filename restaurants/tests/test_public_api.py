"""``GET /restaurants/nearby`` and ``GET /restaurants/{slug}``: public, scoped, absolute URLs."""

from datetime import timedelta
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from menu.models import MenuCategory, MenuItem, Option, OptionGroup
from menu.tests.factories import make_category, make_group, make_item, make_option
from restaurants.models import Restaurant, RestaurantMenuImage
from restaurants.tests.factories import make_restaurant

pytestmark = pytest.mark.django_db

NEARBY = "/api/v1/restaurants/nearby"

# The default test restaurant sits at (25.2001, 55.2701); this point is about 100 m from it.
# 0.001 degrees of latitude is about 111 m.
INSIDE = {"lat": 25.201, "lng": 55.27}
FAR_AWAY = {"lat": 25.3, "lng": 55.4}


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def make_at(slug: str, lat: float, lng: float, **extra: object) -> Restaurant:
    return make_restaurant(slug, latitude=lat, longitude=lng, **extra)


class TestNearby:
    def test_a_restaurant_in_range_is_listed_with_its_distance(
        self, api: APIClient
    ) -> None:
        make_at("cafe-a", 25.2002, 55.2702)

        body = api.get(NEARBY, INSIDE).json()

        assert "nearest" not in body
        [entry] = body["restaurants"]
        assert entry["slug"] == "cafe-a"
        assert entry["name_en"] == "Cafe A"
        assert entry["name_ar"] == "مقهى"
        assert entry["latitude"] == 25.2002
        assert 85 < entry["distance_m"] < 95
        assert entry["logo_url"] is None
        assert set(entry) == {
            "slug",
            "name_en",
            "name_ar",
            "logo_url",
            "latitude",
            "longitude",
            "distance_m",
            "is_open",
        }

    def test_the_nearest_restaurant_comes_first(self, api: APIClient) -> None:
        make_restaurant("cafe-far", latitude=25.2030, longitude=55.2700)
        make_restaurant("cafe-near", latitude=25.2005, longitude=55.2700)

        slugs = [r["slug"] for r in api.get(NEARBY, INSIDE).json()["restaurants"]]

        assert slugs == ["cafe-near", "cafe-far"]

    def test_outside_the_search_distance_the_list_is_empty_and_the_nearest_is_named(
        self, api: APIClient
    ) -> None:
        make_at("cafe-a", 25.2002, 55.2702)
        make_at("cafe-b", 25.9, 55.9)

        body = api.get(NEARBY, FAR_AWAY).json()

        assert body["restaurants"] == []
        nearest = body["nearest"]
        assert nearest["slug"] == "cafe-a"
        assert nearest["distance_m"] > 10_000
        assert "parking_lot" not in nearest
        assert "service_radius_m" not in nearest

    def test_with_no_restaurant_at_all_there_is_nothing_nearest(
        self, api: APIClient
    ) -> None:
        body = api.get(NEARBY, INSIDE).json()

        assert body == {"restaurants": []}

    def test_a_restaurant_serves_only_inside_its_own_service_distance(
        self, api: APIClient
    ) -> None:
        make_at("cafe-a", 25.2001, 55.2701, service_radius_m=50)

        # About 100 m from a restaurant that serves cars within 50 m.
        body = api.get(NEARBY, INSIDE).json()

        assert body["restaurants"] == []
        assert body["nearest"]["slug"] == "cafe-a"
        assert body["nearest"]["service_radius_m"] == 50

    def test_a_restaurant_is_listed_with_its_service_distance_when_it_has_one(
        self, api: APIClient
    ) -> None:
        make_at("cafe-a", 25.2001, 55.2701, service_radius_m=300)

        [entry] = api.get(NEARBY, INSIDE).json()["restaurants"]

        assert entry["service_radius_m"] == 300

    def test_a_restaurant_without_a_service_distance_is_listed_inside_the_search_distance(
        self, api: APIClient
    ) -> None:
        # About 2.2 km north of the customer: inside the default 3 km search distance.
        make_at("cafe-two-km", 25.221, 55.27)
        # About 4.4 km away: outside it.
        make_at("cafe-four-km", 25.241, 55.27)

        slugs = [r["slug"] for r in api.get(NEARBY, INSIDE).json()["restaurants"]]

        assert slugs == ["cafe-two-km"]

    def test_the_search_distance_is_a_setting(
        self, api: APIClient, settings: Any
    ) -> None:
        make_at("cafe-two-km", 25.221, 55.27)
        settings.NEARBY_SEARCH_RADIUS_M = 500

        assert api.get(NEARBY, INSIDE).json()["restaurants"] == []

        settings.NEARBY_SEARCH_RADIUS_M = 5000

        assert len(api.get(NEARBY, INSIDE).json()["restaurants"]) == 1

    def test_the_search_distance_also_limits_a_larger_service_distance(
        self, api: APIClient
    ) -> None:
        # Serves cars within 10 km, but the customer is about 4.4 km away: beyond 3 km.
        make_at("cafe-a", 25.241, 55.27, service_radius_m=10_000)

        body = api.get(NEARBY, INSIDE).json()

        assert body["restaurants"] == []
        assert body["nearest"]["slug"] == "cafe-a"

    def test_an_inactive_restaurant_is_never_listed_or_nearest(
        self, api: APIClient
    ) -> None:
        make_at("cafe-a", 25.2002, 55.2702, is_active=False)

        assert api.get(NEARBY, INSIDE).json() == {"restaurants": []}

    def test_a_suspended_restaurant_is_never_listed_or_nearest(
        self, api: APIClient
    ) -> None:
        make_at("cafe-a", 25.2002, 55.2702, subscription_status="suspended")

        assert api.get(NEARBY, INSIDE).json() == {"restaurants": []}
        assert api.get(NEARBY, FAR_AWAY).json() == {"restaurants": []}

    @pytest.mark.parametrize("status", ["trial", "active"])
    def test_trial_and_active_restaurants_are_listed(
        self, api: APIClient, status: str
    ) -> None:
        make_at("cafe-a", 25.2002, 55.2702, subscription_status=status)

        assert len(api.get(NEARBY, INSIDE).json()["restaurants"]) == 1

    def test_is_open_follows_the_screen_heartbeat(self, api: APIClient) -> None:
        now = timezone.now()
        make_restaurant("online", screen_last_seen_at=now - timedelta(seconds=10))
        make_restaurant("stale", screen_last_seen_at=now - timedelta(seconds=300))
        make_restaurant("never")

        entries = {
            r["slug"]: r["is_open"]
            for r in api.get(NEARBY, INSIDE).json()["restaurants"]
        }

        assert entries == {"online": True, "stale": False, "never": False}

    def test_offline_restaurants_are_hidden_when_the_screen_must_be_online(
        self, api: APIClient, settings: Any
    ) -> None:
        settings.REQUIRE_SCREEN_ONLINE = True
        make_restaurant("online", screen_last_seen_at=timezone.now())
        make_restaurant("offline")

        body = api.get(NEARBY, INSIDE).json()

        assert [r["slug"] for r in body["restaurants"]] == ["online"]

    def test_an_offline_restaurant_is_not_the_nearest_when_it_must_be_online(
        self, api: APIClient, settings: Any
    ) -> None:
        settings.REQUIRE_SCREEN_ONLINE = True
        make_at("offline", 25.2002, 55.2702)

        assert api.get(NEARBY, FAR_AWAY).json() == {"restaurants": []}

    def test_the_logo_is_an_absolute_url(self, api: APIClient) -> None:
        make_restaurant("cafe-a", logo="restaurants/logos/a.png")

        [entry] = api.get(NEARBY, INSIDE).json()["restaurants"]

        assert entry["logo_url"].startswith("http")
        assert entry["logo_url"].endswith("restaurants/logos/a.png")

    def test_the_logo_is_the_public_address_of_the_bucket(
        self, api: APIClient, settings: Any
    ) -> None:
        from config.storage import r2_storage

        settings.STORAGES = {
            **settings.STORAGES,
            "default": r2_storage(
                {
                    "R2_ACCOUNT_ID": "0123456789abcdef",
                    "R2_ACCESS_KEY_ID": "invented-access-key-id",
                    "R2_SECRET_ACCESS_KEY": "invented-secret-access-key",
                    "R2_BUCKET_NAME": "wasli-test-media",
                    "R2_PUBLIC_BASE_URL": "https://pub-1234abcd.r2.dev",
                }
            ),
        }
        make_restaurant("cafe-a", logo="restaurants/logos/a.png")

        [entry] = api.get(NEARBY, INSIDE).json()["restaurants"]

        assert (
            entry["logo_url"] == "https://pub-1234abcd.r2.dev/restaurants/logos/a.png"
        )

    @pytest.mark.parametrize(
        ("params", "attr", "code"),
        [
            ({}, "lat", "required"),
            ({"lat": "25.2"}, "lng", "required"),
            ({"lat": "north", "lng": "55.2"}, "lat", "invalid"),
            ({"lat": "91", "lng": "55.2"}, "lat", "invalid_location"),
            ({"lat": "25.2", "lng": "181"}, "lat", "invalid_location"),
            ({"lat": "nan", "lng": "55.2"}, "lat", "invalid"),
        ],
    )
    def test_a_bad_point_is_a_400(
        self, api: APIClient, params: dict[str, str], attr: str, code: str
    ) -> None:
        response = api.get(NEARBY, params)

        assert response.status_code == 400
        body = response.json()
        assert body["type"] == "validation_error"
        assert any(e["code"] == code and e["attr"] == attr for e in body["errors"])

    def test_no_token_is_needed_and_a_stale_one_is_ignored(
        self, api: APIClient
    ) -> None:
        response = api.get(NEARBY, INSIDE, HTTP_AUTHORIZATION="Token expired")

        assert response.status_code == 200

    def test_the_list_keeps_its_polling_shape_without_pagination(
        self, api: APIClient
    ) -> None:
        make_at("cafe-a", 25.2002, 55.2702)

        assert set(api.get(NEARBY, INSIDE).json()) == {"restaurants"}


class TestDetail:
    def url(self, slug: str) -> str:
        return f"/api/v1/restaurants/{slug}"

    def build_menu(self, restaurant: Restaurant) -> dict[str, Any]:
        drinks = make_category(restaurant, "Drinks")
        MenuCategory.objects.filter(pk=drinks.pk).update(sort_order=2)
        food = make_category(restaurant, "Food")
        MenuCategory.objects.filter(pk=food.pk).update(sort_order=1)
        make_category(restaurant, "Hidden").__class__.objects.filter(
            name_en="Hidden"
        ).update(is_active=False)
        tea = make_item(drinks, "Karak tea", 300)
        sold_out = make_item(food, "Samosa", 200, is_available=False)
        size = make_group(tea, "Size")
        large = make_option(size, "Large", 200, is_default=True)
        return {"tea": tea, "sold_out": sold_out, "size": size, "large": large}

    def test_the_restaurant_comes_with_its_whole_menu(self, api: APIClient) -> None:
        restaurant = make_restaurant(
            "cafe-a", brand_colour="#1A73E8", logo="logos/a.png"
        )
        RestaurantMenuImage.objects.create(
            restaurant=restaurant, image="menu/2.jpg", sort_order=2, caption_en="Two"
        )
        RestaurantMenuImage.objects.create(
            restaurant=restaurant, image="menu/1.jpg", sort_order=1, caption_en="One"
        )
        rows = self.build_menu(restaurant)

        response = api.get(self.url("cafe-a"))

        assert response.status_code == 200
        body = response.json()
        assert body["slug"] == "cafe-a"
        assert body["brand_colour"] == "#1A73E8"
        assert body["currency"] == "AED"
        assert body["logo_url"].startswith("http")
        assert "parking_lot" not in body
        assert "service_radius_m" not in body
        assert [i["caption_en"] for i in body["menu_images"]] == ["One", "Two"]
        assert body["menu_images"][0]["image_url"].startswith("http")
        # Categories follow their sort order; the inactive one is not shown.
        assert [c["name_en"] for c in body["menu"]] == ["Food", "Drinks"]
        food, drinks = body["menu"]
        # An unavailable item stays on the menu with its flag.
        assert food["items"][0]["name_en"] == "Samosa"
        assert food["items"][0]["is_available"] is False
        [tea] = drinks["items"]
        assert tea["id"] == str(rows["tea"].pk)
        assert tea["price_minor"] == 300
        assert tea["image_url"] is None
        [group] = tea["option_groups"]
        assert (group["min_select"], group["max_select"]) == (0, 1)
        assert group["options"] == [
            {
                "id": str(rows["large"].pk),
                "name_en": "Large",
                "name_ar": "كبير",
                "price_delta_minor": 200,
                "is_available": True,
                "is_default": True,
            }
        ]

    def test_the_service_distance_is_shown_when_the_restaurant_has_one(
        self, api: APIClient
    ) -> None:
        make_restaurant("cafe-a", service_radius_m=300)

        assert api.get(self.url("cafe-a")).json()["service_radius_m"] == 300

    def test_a_category_has_an_optional_picture_like_an_item(
        self, api: APIClient
    ) -> None:
        restaurant = make_restaurant("cafe-pic")
        pictured = make_category(restaurant, "Burgers", image="menu/burgers.webp")
        make_category(restaurant, "Drinks")
        make_item(pictured, "Chicken burger")

        body = api.get(self.url("cafe-pic")).json()

        burgers, drinks = body["menu"]
        assert burgers["image_url"].startswith("http")
        assert burgers["image_url"].endswith("menu/burgers.webp")
        assert drinks["image_url"] is None

    def test_another_restaurants_menu_never_leaks_in(self, api: APIClient) -> None:
        a, b = make_restaurant("cafe-a"), make_restaurant("cafe-b")
        make_item(make_category(a), "Only at A")
        make_item(make_category(b), "Only at B")

        body = api.get(self.url("cafe-a")).json()

        names = [i["name_en"] for c in body["menu"] for i in c["items"]]
        assert names == ["Only at A"]

    def test_an_unknown_restaurant_is_a_404_in_the_error_body(
        self, api: APIClient
    ) -> None:
        response = api.get(self.url("nowhere"))

        assert response.status_code == 404
        body = response.json()
        assert body["type"] == "client_error"
        assert body["errors"][0]["code"] == "not_found"

    def test_an_inactive_restaurant_is_a_404(self, api: APIClient) -> None:
        make_restaurant("cafe-a", is_active=False)

        assert api.get(self.url("cafe-a")).status_code == 404

    def test_a_suspended_restaurant_is_a_404(self, api: APIClient) -> None:
        make_restaurant("cafe-a", subscription_status="suspended")

        assert api.get(self.url("cafe-a")).status_code == 404

    def test_a_restaurant_is_visible_again_when_reactivated(
        self, api: APIClient
    ) -> None:
        restaurant = make_restaurant("cafe-a", subscription_status="suspended")
        Restaurant.objects.filter(pk=restaurant.pk).update(subscription_status="active")

        assert api.get(self.url("cafe-a")).status_code == 200

    def test_nearby_is_not_read_as_a_slug(self, api: APIClient) -> None:
        response = api.get(NEARBY, INSIDE)

        assert response.status_code == 200
        assert "restaurants" in response.json()

    def test_the_menu_is_read_in_a_fixed_number_of_queries(
        self, api: APIClient, django_assert_max_num_queries: Any
    ) -> None:
        restaurant = make_restaurant("cafe-a")
        for number in range(4):
            category = make_category(restaurant, f"Category {number}")
            for item_number in range(3):
                item = make_item(category, f"Item {number}-{item_number}")
                make_option(make_group(item, f"Group {number}-{item_number}"))

        with django_assert_max_num_queries(8):
            assert api.get(self.url("cafe-a")).status_code == 200


class TestReservedSlug:
    def test_nearby_cannot_be_a_slug(self) -> None:
        with pytest.raises(ValidationError):
            make_restaurant("nearby")

    def test_the_admin_form_check_refuses_it_too(self) -> None:
        restaurant = Restaurant(slug="nearby")

        with pytest.raises(ValidationError) as error:
            restaurant.clean()

        assert "slug" in error.value.message_dict


class TestEnglishOnlyRestaurant:
    """No Arabic text is stored, yet every Arabic field of the API is filled with the English
    text, so a client never receives an empty name."""

    def test_the_detail_falls_back_to_english_for_every_arabic_field(
        self, api: APIClient
    ) -> None:
        restaurant = make_restaurant("gulf-food", name_ar="")
        category = MenuCategory.objects.create(restaurant=restaurant, name_en="Burgers")
        item = MenuItem.objects.create(
            category=category,
            name_en="Chicken burger",
            description_en="Grilled, with fries",
            price_minor=1800,
        )
        group = OptionGroup.objects.create(item=item, name_en="Size")
        Option.objects.create(group=group, name_en="Large", price_delta_minor=300)
        RestaurantMenuImage.objects.create(
            restaurant=restaurant, image="menu/1.jpg", caption_en="Main menu"
        )

        body = api.get("/api/v1/restaurants/gulf-food").json()

        assert body["name_ar"] == "Gulf Food"
        [image] = body["menu_images"]
        assert image["caption_ar"] == "Main menu"
        [cat] = body["menu"]
        assert cat["name_ar"] == "Burgers"
        [entry] = cat["items"]
        assert entry["name_ar"] == "Chicken burger"
        assert entry["description_ar"] == "Grilled, with fries"
        [grp] = entry["option_groups"]
        assert grp["name_ar"] == "Size"
        assert grp["options"][0]["name_ar"] == "Large"

    def test_nearby_falls_back_to_english_for_the_name(self, api: APIClient) -> None:
        make_at("gulf-food", 25.2002, 55.2702, name_ar="")

        [entry] = api.get(NEARBY, INSIDE).json()["restaurants"]

        assert entry["name_en"] == "Gulf Food"
        assert entry["name_ar"] == "Gulf Food"

    def test_an_arabic_text_is_returned_as_it_was_entered(self, api: APIClient) -> None:
        restaurant = make_restaurant("cafe-ar", name_ar="مقهى")
        item = make_item(make_category(restaurant), "Karak tea")
        item.description_en = "Strong"
        item.description_ar = "قوي"
        item.save()

        body = api.get("/api/v1/restaurants/cafe-ar").json()

        assert body["name_ar"] == "مقهى"
        entry = body["menu"][0]["items"][0]
        assert entry["name_ar"] == "شاي"
        assert entry["description_ar"] == "قوي"


class TestNestedMenu:
    """Categories may sit inside categories (up to three levels). The list stays flat, depth
    first, and a subcategory carries the id of its parent."""

    def url(self, slug: str) -> str:
        return f"/api/v1/restaurants/{slug}"

    def test_the_menu_is_flat_depth_first_with_the_parent_id_on_subcategories(
        self, api: APIClient
    ) -> None:
        restaurant = make_restaurant("cafe-a")
        drinks = make_category(restaurant, "Drinks", sort_order=2)
        burgers = make_category(restaurant, "Burgers", sort_order=1)
        grilled = make_category(restaurant, "Grilled", parent=burgers)
        chicken = make_category(restaurant, "Chicken", parent=grilled)
        make_item(burgers, "House burger", 1500)
        make_item(chicken, "Chicken burger", 1800)

        body = api.get(self.url("cafe-a")).json()

        assert [c["name_en"] for c in body["menu"]] == [
            "Burgers",
            "Grilled",
            "Chicken",
            "Drinks",
        ]
        by_name = {c["name_en"]: c for c in body["menu"]}
        assert "parent_id" not in by_name["Burgers"]
        assert "parent_id" not in by_name["Drinks"]
        assert by_name["Grilled"]["parent_id"] == str(burgers.pk)
        assert by_name["Chicken"]["parent_id"] == str(grilled.pk)
        assert [i["name_en"] for i in by_name["Burgers"]["items"]] == ["House burger"]
        assert [i["name_en"] for i in by_name["Chicken"]["items"]] == ["Chicken burger"]
        assert by_name["Drinks"]["items"] == []
        assert str(drinks.pk) == by_name["Drinks"]["id"]

    def test_hiding_a_category_hides_its_subcategories_and_their_items(
        self, api: APIClient
    ) -> None:
        restaurant = make_restaurant("cafe-a")
        burgers = make_category(restaurant, "Burgers", is_active=False)
        grilled = make_category(restaurant, "Grilled", parent=burgers)
        make_item(grilled, "Hidden burger")
        make_category(restaurant, "Drinks")

        body = api.get(self.url("cafe-a")).json()

        assert [c["name_en"] for c in body["menu"]] == ["Drinks"]

    def test_a_menu_without_subcategories_is_unchanged(self, api: APIClient) -> None:
        restaurant = make_restaurant("cafe-a")
        make_item(make_category(restaurant, "Drinks"), "Karak tea")

        [category] = api.get(self.url("cafe-a")).json()["menu"]

        # No `parent_id` for a top-level category; `image_url` is always there (null without a picture).
        assert set(category) == {"id", "name_en", "name_ar", "image_url", "items"}
        assert category["image_url"] is None
