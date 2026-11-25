"""Every route under ``/api/v1/``. Each app owns its own ``urls.py``."""

from django.urls import include, path

urlpatterns = [
    path("", include("core.urls")),
    path("", include("restaurants.urls")),
    path("", include("restaurants.staff_urls")),
    path("", include("customers.urls")),
    path("", include("chat.urls")),
    path("", include("orders.urls")),
]
