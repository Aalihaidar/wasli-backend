from users.models import User

from .models import StaffMembership


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
