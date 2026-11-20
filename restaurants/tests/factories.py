"""Small helpers that build valid rows for tests (invented data only)."""

from core.permissions import Role
from restaurants.models import Restaurant, StaffMembership
from users.models import User

PASSWORD = "s3cret-pass-4-tests"


def make_restaurant(slug: str = "cafe-one", **extra: object) -> Restaurant:
    values: dict[str, object] = {
        "name_en": slug.replace("-", " ").title(),
        "name_ar": "مقهى",
        "latitude": 25.2001,
        "longitude": 55.2701,
        **extra,
    }
    return Restaurant.objects.create(slug=slug, **values)


def make_user(username: str) -> User:
    return User.objects.create_user(username, PASSWORD)


def make_member(
    restaurant: Restaurant,
    username: str,
    role: Role = Role.CASHIER,
    *,
    is_active: bool = True,
) -> StaffMembership:
    return StaffMembership.objects.create(
        restaurant=restaurant,
        user=make_user(username),
        role=role.value,
        is_active=is_active,
    )
