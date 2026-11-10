from django.urls import path

from .views import NearbyRestaurantsView, RestaurantDetailView

urlpatterns = [
    # "nearby" must stay before the slug route, and is not a valid slug (Restaurant.clean).
    path(
        "restaurants/nearby", NearbyRestaurantsView.as_view(), name="restaurants-nearby"
    ),
    path(
        "restaurants/<slug:slug>",
        RestaurantDetailView.as_view(),
        name="restaurants-detail",
    ),
]
