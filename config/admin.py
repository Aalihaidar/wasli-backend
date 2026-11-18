"""The Django admin of Wasli: the platform team's tool (restaurants never see it).

Built-in polish only (ADR 0013): the branding, a fixed order of the sections, the environment in
the header so staging is never taken for production, and a few counters on the first page. The
look itself is ``static/admin/css/wasli.css`` and the two templates under ``templates/admin/``.
"""

from typing import Any

from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest
from django.template.response import TemplateResponse

from .dashboard import dashboard_cards

# The sections, in the order the platform team works: restaurants and their menu, the orders,
# the customers and their conversations, then the technical ones.
APP_ORDER = (
    "restaurants",
    "menu",
    "orders",
    "customers",
    "chat",
    "messaging",
    "assistant",
    "users",
    "auth",
    "authtoken",
    "django_celery_beat",
)
APP_NAMES = {
    "chat": "Conversations",
    "assistant": "Assistant",
    "auth": "Groups and permissions",
    "authtoken": "API tokens",
    "django_celery_beat": "Scheduled tasks",
}
# The order of the models inside a section (a model not listed follows, alphabetically).
MODEL_ORDER = {
    "restaurants": ("Restaurant", "ParkingLot", "StaffMembership"),
    "menu": ("MenuCategory", "MenuItem", "OptionGroup"),
    "customers": ("Customer", "CustomerBlock", "CustomerSession"),
}


class WasliAdminSite(admin.AdminSite):
    site_header = "Wasli administration"
    site_title = "Wasli admin"
    index_title = "Platform administration"

    def each_context(self, request: HttpRequest) -> dict[str, Any]:
        context = super().each_context(request)
        # Shown next to the title: local, staging or production.
        context["wasli_environment"] = settings.ENVIRONMENT
        return context

    def get_app_list(
        self, request: HttpRequest, app_label: str | None = None
    ) -> list[dict[str, Any]]:
        apps = super().get_app_list(request, app_label)
        for app in apps:
            app["name"] = APP_NAMES.get(app["app_label"], app["name"])
            order = MODEL_ORDER.get(app["app_label"], ())
            app["models"].sort(
                key=lambda m, order=order: (
                    order.index(m["object_name"])
                    if m["object_name"] in order
                    else len(order),
                    m["name"],
                )
            )
        apps.sort(
            key=lambda a: (
                APP_ORDER.index(a["app_label"])
                if a["app_label"] in APP_ORDER
                else len(APP_ORDER),
                a["name"],
            )
        )
        return apps

    def index(
        self, request: HttpRequest, extra_context: dict[str, Any] | None = None
    ) -> TemplateResponse:
        extra = {"wasli_cards": dashboard_cards(), **(extra_context or {})}
        return super().index(request, extra)
