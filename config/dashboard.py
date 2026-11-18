"""The counters on the first page of the Django admin: what the platform team looks at first.

Counts only: nothing here shows a customer's name, contact, car or position.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

# "Today" is the day in the UAE, where every restaurant is.
DAY_ZONE = ZoneInfo("Asia/Dubai")
# A restaurant's site counts as online when it polled this recently (restaurants.services).
ONLINE_SECONDS = 60


@dataclass(frozen=True)
class Card:
    label: str
    value: int
    hint: str = ""
    url: str = ""


def start_of_today() -> datetime:
    now = timezone.now().astimezone(DAY_ZONE)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def dashboard_cards() -> list[Card]:
    # Imported here: the admin site is created before the apps' models are ready.
    from assistant.models import AICallLog
    from customers.models import Customer
    from orders.models import Order, OrderStatus
    from restaurants.models import Restaurant

    now = timezone.now()
    online = Restaurant.objects.filter(
        is_active=True,
        screen_last_seen_at__gte=now - timedelta(seconds=ONLINE_SECONDS),
    ).count()
    verified = Customer.objects.filter(
        Q(user__email_verified_at__isnull=False)
        | Q(user__phone_verified_at__isnull=False)
    ).count()
    failed = AICallLog.objects.filter(
        created_at__gte=now - timedelta(hours=24)
    ).exclude(outcome="ok")
    return [
        Card(
            "Restaurants",
            Restaurant.objects.filter(is_active=True).count(),
            f"{online} online now",
            reverse("admin:restaurants_restaurant_changelist") + "?is_active__exact=1",
        ),
        Card(
            "Orders waiting",
            Order.objects.filter(status=OrderStatus.PLACED).count(),
            "placed, not yet answered",
            reverse("admin:orders_order_changelist") + "?status__exact=placed",
        ),
        Card(
            "Orders today",
            Order.objects.filter(placed_at__gte=start_of_today()).count(),
            "since midnight, UAE time",
            reverse("admin:orders_order_changelist"),
        ),
        Card(
            "Customers",
            verified,
            "with a verified contact",
            reverse("admin:customers_customer_changelist"),
        ),
        Card(
            "Assistant calls",
            AICallLog.objects.filter(created_at__gte=now - timedelta(hours=24)).count(),
            f"last 24 hours, {failed.count()} failed",
            reverse("admin:assistant_aicalllog_changelist"),
        ),
    ]
