import pytest
from django.test import Client
from django.urls import reverse

from menu.models import MenuItem, Option, OptionGroup
from menu.tests.factories import make_category, make_group, make_item, make_option
from restaurants.tests.factories import PASSWORD, make_restaurant
from users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client() -> Client:
    User.objects.create_superuser("owner", PASSWORD, email="owner@example.com")
    client = Client()
    assert client.login(username="owner", password=PASSWORD)
    return client


def test_the_pages_load(admin_client: Client) -> None:
    category = make_category(make_restaurant("cafe-a"))
    item = make_item(category, aliases=["karak"])
    group = make_group(item)
    make_option(group)
    pages = [
        reverse("admin:menu_menucategory_changelist"),
        reverse("admin:menu_menucategory_add"),
        reverse("admin:menu_menucategory_change", args=[category.pk]),
        reverse("admin:menu_menuitem_changelist"),
        reverse("admin:menu_menuitem_add"),
        reverse("admin:menu_menuitem_change", args=[item.pk]),
        reverse("admin:menu_optiongroup_changelist"),
        reverse("admin:menu_optiongroup_add"),
        reverse("admin:menu_optiongroup_change", args=[group.pk]),
    ]

    for page in pages:
        assert admin_client.get(page).status_code == 200, page


def test_the_item_list_shows_the_price_in_aed(admin_client: Client) -> None:
    make_item(make_category(make_restaurant("cafe-a")), price_minor=1250)

    response = admin_client.get(reverse("admin:menu_menuitem_changelist"))

    assert "12.50" in response.content.decode()


def test_an_item_is_added_with_aed_and_aliases(admin_client: Client) -> None:
    restaurant = make_restaurant("cafe-a")
    category = make_category(restaurant)

    response = admin_client.post(
        reverse("admin:menu_menuitem_add"),
        {
            "category": str(category.pk),
            "name_en": "Karak tea",
            "name_ar": "شاي كرك",
            "price_minor": "12.50",
            "aliases": "karak\nchai",
            "is_available": "on",
            "sort_order": "0",
            "option_groups-TOTAL_FORMS": "0",
            "option_groups-INITIAL_FORMS": "0",
        },
    )

    assert response.status_code == 302
    item = MenuItem.objects.get(name_en="Karak tea")
    assert item.price_minor == 1250
    assert item.aliases == ["karak", "chai"]
    assert item.restaurant_id == restaurant.pk


def test_a_bad_price_keeps_the_form_open(admin_client: Client) -> None:
    category = make_category(make_restaurant("cafe-a"))

    response = admin_client.post(
        reverse("admin:menu_menuitem_add"),
        {
            "category": str(category.pk),
            "name_en": "Tea",
            "name_ar": "شاي",
            "price_minor": "12.555",
            "sort_order": "0",
            "option_groups-TOTAL_FORMS": "0",
            "option_groups-INITIAL_FORMS": "0",
        },
    )

    assert response.status_code == 200
    assert not MenuItem.objects.exists()


def test_options_are_added_on_the_group_page(admin_client: Client) -> None:
    restaurant = make_restaurant("cafe-a")
    group = make_group(make_item(make_category(restaurant)), max_select=2)

    response = admin_client.post(
        reverse("admin:menu_optiongroup_change", args=[group.pk]),
        {
            "item": str(group.item.pk),
            "name_en": group.name_en,
            "name_ar": group.name_ar,
            "min_select": "0",
            "max_select": "2",
            "sort_order": "0",
            "options-TOTAL_FORMS": "1",
            "options-INITIAL_FORMS": "0",
            "options-0-name_en": "Small",
            "options-0-name_ar": "صغير",
            "options-0-price_delta_minor": "-1.00",
            "options-0-is_available": "on",
            "options-0-sort_order": "0",
        },
    )

    assert response.status_code == 302
    option = Option.objects.get(name_en="Small")
    assert option.price_delta_minor == -100
    assert option.restaurant_id == restaurant.pk
    assert OptionGroup.objects.get(pk=group.pk).options.count() == 1


class TestPolish:
    def test_an_item_shows_its_photo_in_the_list_and_a_preview_under_the_photo_field(
        self, admin_client: Client
    ) -> None:
        category = make_category(make_restaurant("cafe-a"))
        item = make_item(category, "Karak tea", image="menu/items/karak.jpg")

        listing = admin_client.get(
            reverse("admin:menu_menuitem_changelist")
        ).content.decode()
        form = admin_client.get(
            reverse("admin:menu_menuitem_change", args=[item.pk])
        ).content.decode()

        assert "menu/items/karak.jpg" in listing and 'class="wasli-thumb"' in listing
        assert "wasli-thumb--large" in form
        assert form.index('name="image"') < form.index("wasli-thumb--large")

    def test_the_preview_field_follows_the_photo_field(
        self, admin_client: Client
    ) -> None:
        from django.contrib import admin
        from django.test import RequestFactory

        model_admin = admin.site._registry[MenuItem]
        request = RequestFactory().get("/")
        request.user = User.objects.get(username="owner")

        fields = model_admin.get_fields(request)

        assert fields.index("photo_preview") == fields.index("image") + 1
        assert fields.count("photo_preview") == 1

    def test_the_item_name_is_the_link_and_not_the_photo(
        self, admin_client: Client
    ) -> None:
        item = make_item(make_category(make_restaurant("cafe-a")), "Karak tea")

        page = admin_client.get(
            reverse("admin:menu_menuitem_changelist")
        ).content.decode()

        link = reverse("admin:menu_menuitem_change", args=[item.pk])
        assert f'<a href="{link}">Karak tea</a>' in page

    def test_a_category_page_lists_its_items_with_their_prices_in_aed(
        self, admin_client: Client
    ) -> None:
        category = make_category(make_restaurant("cafe-a"))
        make_item(category, "Karak tea", price_minor=1250)

        page = admin_client.get(
            reverse("admin:menu_menucategory_change", args=[category.pk])
        ).content.decode()

        assert "Karak tea" in page
        assert 'value="12.50"' in page
        assert "Price (AED)" in page

    def test_an_item_is_added_from_its_category_page(
        self, admin_client: Client
    ) -> None:
        restaurant = make_restaurant("cafe-a")
        category = make_category(restaurant)
        url = reverse("admin:menu_menucategory_change", args=[category.pk])

        response = admin_client.post(
            url,
            {
                "restaurant": str(restaurant.pk),
                "name_en": category.name_en,
                "name_ar": category.name_ar,
                "sort_order": "0",
                "is_active": "on",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-name_en": "Cheese sandwich",
                "items-0-name_ar": "ساندويتش جبنة",
                "items-0-price_minor": "7.50",
                "items-0-is_available": "on",
                "items-0-sort_order": "1",
            },
        )

        assert response.status_code == 302, response.content.decode()[:500]
        item = MenuItem.objects.get(name_en="Cheese sandwich")
        assert item.price_minor == 750  # typed in AED, stored in fils
        assert item.category_id == category.pk
        assert item.restaurant_id == restaurant.pk  # follows its category

    def test_a_bad_price_is_refused_on_the_category_page(
        self, admin_client: Client
    ) -> None:
        restaurant = make_restaurant("cafe-a")
        category = make_category(restaurant)

        response = admin_client.post(
            reverse("admin:menu_menucategory_change", args=[category.pk]),
            {
                "restaurant": str(restaurant.pk),
                "name_en": category.name_en,
                "name_ar": category.name_ar,
                "sort_order": "0",
                "is_active": "on",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-name_en": "Free lunch",
                "items-0-name_ar": "غداء",
                "items-0-price_minor": "twelve",
                "items-0-sort_order": "0",
            },
        )

        assert response.status_code == 200  # the form again, with the error
        assert not MenuItem.objects.filter(name_en="Free lunch").exists()

    def test_the_item_page_still_edits_everything_else(
        self, admin_client: Client
    ) -> None:
        item = make_item(make_category(make_restaurant("cafe-a")), aliases=["karak"])

        page = admin_client.get(
            reverse("admin:menu_menuitem_change", args=[item.pk])
        ).content.decode()

        assert "karak" in page and "description_en" in page and 'name="aliases"' in page
