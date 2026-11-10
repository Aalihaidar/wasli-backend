from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db.models import QuerySet
from django.utils import timezone

from core.geo import haversine_m
from users.models import User

from .models import Restaurant, StaffMembership

# A restaurant's screen counts as online when its site polled within this many seconds.
SCREEN_ONLINE_SECONDS = 60


def resolve_membership(
    user: User, restaurant_slug: str | None = None
) -> StaffMembership | None:
    """The membership a staff request acts under, or None when there is no single one.

    Only an active member of an active restaurant counts. A user with several memberships
    must say which restaurant (by slug); without a slug the choice is ambiguous and nothing
    is returned rather than guessing.
    """
    memberships = StaffMembership.objects.filter(
        user=user, is_active=True, restaurant__is_active=True
    ).select_related("restaurant")
    if restaurant_slug is not None:
        memberships = memberships.filter(restaurant__slug=restaurant_slug)
    found = list(memberships[:2])
    return found[0] if len(found) == 1 else None


def public_restaurants() -> QuerySet[Restaurant]:
    """The restaurants a customer can see: active ones whose subscription is not suspended.

    The public endpoints (nearby and the detail) start from this, so a deactivated or a
    suspended restaurant is never listed and its page is a 404.
    """
    return Restaurant.objects.filter(is_active=True).exclude(
        subscription_status=Restaurant.SubscriptionStatus.SUSPENDED
    )


def screen_is_online(restaurant: Restaurant, now: datetime | None = None) -> bool:
    """True when the restaurant's site polled in the last minute, so it can take an order."""
    seen = restaurant.screen_last_seen_at
    if seen is None:
        return False
    return (now or timezone.now()) - seen <= timedelta(seconds=SCREEN_ONLINE_SECONDS)


@dataclass(frozen=True)
class NearbyEntry:
    restaurant: Restaurant
    distance_m: int  # from the customer to the restaurant
    is_open: bool


@dataclass(frozen=True)
class NearbyResult:
    restaurants: list[NearbyEntry]
    # Only when no restaurant is in range: the closest one, so the app can say how far it is.
    nearest: NearbyEntry | None


def find_nearby(
    lat: float,
    lng: float,
    *,
    require_screen_online: bool,
    now: datetime | None = None,
) -> NearbyResult:
    """Visible restaurants (``public_restaurants``) whose parking lot is in range of the point,
    nearest first.

    A restaurant is in range when the point is within the lot's ``radius_m`` of the lot's
    centre. ``distance_m`` is the distance to the restaurant itself. When
    ``require_screen_online`` is set, a restaurant whose screen is offline is left out
    (and cannot be the ``nearest`` either).
    """
    in_range: list[NearbyEntry] = []
    everyone: list[NearbyEntry] = []
    restaurants = public_restaurants().select_related("parking_lot")
    for restaurant in restaurants:
        is_open = screen_is_online(restaurant, now)
        if require_screen_online and not is_open:
            continue
        entry = NearbyEntry(
            restaurant=restaurant,
            distance_m=round(
                haversine_m(lat, lng, restaurant.latitude, restaurant.longitude)
            ),
            is_open=is_open,
        )
        everyone.append(entry)
        lot = restaurant.parking_lot
        if haversine_m(lat, lng, lot.latitude, lot.longitude) <= lot.radius_m:
            in_range.append(entry)

    def order(entry: NearbyEntry) -> tuple[int, str]:
        return entry.distance_m, entry.restaurant.slug

    in_range.sort(key=order)
    if in_range:
        return NearbyResult(restaurants=in_range, nearest=None)
    return NearbyResult(restaurants=[], nearest=min(everyone, key=order, default=None))
