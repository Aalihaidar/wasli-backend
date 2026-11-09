"""Small helpers that build valid rows for tests (invented data only)."""

from core.permissions import Role
from restaurants.models import ParkingLot, Restaurant, StaffMembership
from users.models import User

PASSWORD = "s3cret-pass-4-tests"


def make_lot(name: str = "Marina Lot", **extra: object) -> ParkingLot:
    values: dict[str, object] = {"latitude": 25.2, "longitude": 55.27, **extra}
    return ParkingLot.objects.create(name=name, **values)


def make_restaurant(
    slug: str = "cafe-one", lot: ParkingLot | None = None, **extra: object
) -> Restaurant:
    values: dict[str, object] = {
        "name_en": slug.replace("-", " ").title(),
        "name_ar": "مقهى",
        "latitude": 25.2001,
        "longitude": 55.2701,
        **extra,
    }
    return Restaurant.objects.create(
        slug=slug,
        parking_lot=lot or make_lot(name=f"Lot of {slug}"),
        **values,
    )


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
