"""The Wasli admin: branding, the order of the sections, the environment badge and the counters
on the first page (config/admin.py, config/dashboard.py, ADR 0013)."""

import re
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.contrib import admin
from django.contrib.staticfiles import finders
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone

from config.admin import APP_ORDER
from config.dashboard import dashboard_cards, start_of_today
from customers.tests.factories import PASSWORD, make_customer
from orders.tests.factories import make_order
from restaurants.tests.factories import make_restaurant
from users.models import User

pytestmark = pytest.mark.django_db

CSS = Path(__file__).resolve().parents[2] / "static" / "admin" / "css" / "wasli.css"


@pytest.fixture
def admin_client() -> Client:
    User.objects.create_superuser("owner", PASSWORD, email="owner@example.com")
    client = Client()
    assert client.login(username="owner", password=PASSWORD)
    return client


def index(client: Client) -> str:
    response = client.get(reverse("admin:index"))
    assert response.status_code == 200
    return response.content.decode()


def card(label: str) -> Any:
    [found] = [c for c in dashboard_cards() if c.label == label]
    return found


class TestBranding:
    def test_the_site_has_the_wasli_names(self, admin_client: Client) -> None:
        page = index(admin_client)

        assert "Wasli administration" in page
        assert "Platform administration" in page
        assert "Django administration" not in page
        assert "<title>Platform administration | Wasli admin</title>" in page

    def test_the_login_page_is_branded_and_keeps_the_theme_toggle(
        self, client: Client
    ) -> None:
        response = client.get(reverse("admin:login"))

        page = response.content.decode()
        assert response.status_code == 200
        assert "Wasli administration" in page
        assert "theme-toggle" in page

    def test_the_stylesheet_is_linked_and_found(self, admin_client: Client) -> None:
        assert "/static/admin/css/wasli.css" in index(admin_client)
        assert finders.find("admin/css/wasli.css")

    def test_the_stylesheet_recolours_both_themes_and_loads_only_its_font(
        self,
    ) -> None:
        css = CSS.read_text()

        assert "--wasli-brand" in css
        assert "@media (prefers-color-scheme: dark)" in css
        assert 'html[data-theme="dark"]' in css and 'html[data-theme="light"]' in css
        # The only files it loads are the two Rubik font files, from this site: no image and
        # no outside address, so nothing for a strict Content Security Policy to block.
        assert re.findall(r'url\("([^"]+)"\)', css) == [
            "../fonts/rubik-latin.woff2",
            "../fonts/rubik-arabic.woff2",
        ]
        assert "url(" not in css.replace('url("', "")
        assert "http" not in css
        for token in ("--secondary", "--link-fg", "--breadcrumbs-bg", "--wasli-ok-bg"):
            assert token in css

    def test_the_stylesheet_uses_the_design_colours(self) -> None:
        """The values of docs/design.md: navy primary, mustard accent, off-white page."""
        css = CSS.read_text()

        for colour in (
            "#1f2a44",
            "#121a2e",
            "#f2b705",
            "#fafaf7",
            "#5b6475",
            "#2c4fa3",
        ):
            assert colour in css

    @pytest.mark.parametrize(
        "name", ["rubik-latin.woff2", "rubik-arabic.woff2", "Rubik-OFL.txt"]
    )
    def test_the_font_files_and_their_licence_are_shipped(self, name: str) -> None:
        assert finders.find(f"admin/fonts/{name}")

    @pytest.mark.parametrize("environment", ["local", "staging", "production"])
    def test_the_environment_is_shown_next_to_the_title(
        self, admin_client: Client, settings: Any, environment: str
    ) -> None:
        settings.ENVIRONMENT = environment

        page = index(admin_client)

        assert (
            f'class="wasli-env wasli-env--{environment}">{environment}</span>' in page
        )

    def test_the_environment_is_shown_on_the_login_page_too(
        self, client: Client, settings: Any
    ) -> None:
        settings.ENVIRONMENT = "production"

        assert (
            "wasli-env--production"
            in client.get(reverse("admin:login")).content.decode()
        )

    def test_the_templates_carry_no_inline_style(self, admin_client: Client) -> None:
        """So the pages keep working when the Content Security Policy is enforced."""
        assert (
            "style="
            not in index(admin_client)
            .split('<div id="content"', 1)[1]
            .split("</body>")[0]
        )


class TestSectionOrder:
    def app_labels(self) -> list[str]:
        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser(
            "root", PASSWORD, email="root@example.com"
        )
        return [a["app_label"] for a in admin.site.get_app_list(request)]

    def test_sections_follow_how_the_platform_team_works(self) -> None:
        labels = self.app_labels()

        wanted = [label for label in APP_ORDER if label in labels]
        assert labels[: len(wanted)] == wanted
        assert (
            labels.index("restaurants") < labels.index("menu") < labels.index("orders")
        )
        assert labels.index("orders") < labels.index("customers") < labels.index("chat")
        assert (
            labels.index("messaging")
            < labels.index("assistant")
            < labels.index("authtoken")
        )

    def test_technical_sections_come_last(self) -> None:
        labels = self.app_labels()

        for technical in ("users", "auth", "authtoken"):
            assert labels.index(technical) > labels.index("customers")

    def test_sections_have_plain_names(self, admin_client: Client) -> None:
        page = index(admin_client)

        for name in ("Conversations", "API tokens", "Groups and permissions"):
            assert name in page

    def test_models_inside_a_section_follow_their_order(self) -> None:
        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser(
            "root", PASSWORD, email="root@example.com"
        )

        apps = {a["app_label"]: a for a in admin.site.get_app_list(request)}

        assert [m["object_name"] for m in apps["restaurants"]["models"]][:2] == [
            "Restaurant",
            "StaffMembership",
        ]
        assert [m["object_name"] for m in apps["menu"]["models"]][:3] == [
            "MenuCategory",
            "MenuItem",
            "OptionGroup",
        ]


class TestCounters:
    def test_they_count_restaurants_and_those_online(self) -> None:
        make_restaurant("cafe-a", screen_last_seen_at=timezone.now())
        make_restaurant(
            "cafe-b", screen_last_seen_at=timezone.now() - timedelta(minutes=5)
        )
        make_restaurant("cafe-c", is_active=False)

        restaurants = card("Restaurants")

        assert restaurants.value == 2
        assert restaurants.hint == "1 online now"
        assert restaurants.url.endswith("?is_active__exact=1")

    def test_they_count_the_orders_waiting_and_today(self) -> None:
        waiting = make_order()
        make_order(status="accepted")
        old = make_order()
        type(old).objects.filter(pk=old.pk).update(
            placed_at=start_of_today() - timedelta(days=2)
        )

        assert card("Orders waiting").value == 2  # the two that are still placed
        assert card("Orders today").value == 2  # not the one from two days ago
        assert waiting.pk != old.pk

    def test_the_day_starts_at_midnight_in_the_uae(self) -> None:
        start = start_of_today()

        assert (start.hour, start.minute, start.second) == (0, 0, 0)
        assert str(start.tzinfo) == "Asia/Dubai"

    def test_they_count_customers_with_a_verified_contact(self) -> None:
        verified = make_customer("sara@example.com")
        verified.user.email_verified_at = timezone.now()
        verified.user.save(update_fields=["email_verified_at"])
        make_customer("omar@example.com")  # signed up, never verified

        assert card("Customers").value == 1

    def test_they_count_the_assistants_calls_and_failures(self) -> None:
        from assistant.models import AICallLog

        for outcome in ("ok", "ok", "timeout"):
            AICallLog.objects.create(
                provider="fake",
                purpose="classify_reply",
                input_kind="text",
                outcome=outcome,
            )

        calls = card("Assistant calls")

        assert calls.value == 3
        assert "1 failed" in calls.hint

    def test_every_card_links_into_the_admin(self) -> None:
        for each in dashboard_cards():
            assert each.url.startswith("/admin/")

    def test_the_first_page_shows_the_cards_and_no_personal_data(
        self, admin_client: Client
    ) -> None:
        make_order()
        customer = make_customer("private.person@example.com", name="Private Person")
        customer.user.email_verified_at = timezone.now()
        customer.user.save(update_fields=["email_verified_at"])

        page = index(admin_client)

        for label in (
            "Restaurants",
            "Orders waiting",
            "Orders today",
            "Customers",
            "Assistant calls",
        ):
            assert f">{label}<" in page
        assert 'class="wasli-card"' in page
        assert "private.person@example.com" not in page and "Private Person" not in page

    def test_the_first_page_still_works_with_nothing_in_the_database(
        self, admin_client: Client
    ) -> None:
        assert "wasli-card__value" in index(admin_client)

    def test_the_first_page_needs_a_login(self, client: Client) -> None:
        response = client.get(reverse("admin:index"))

        assert response.status_code == 302
        assert "/admin/login/" in response["Location"]
