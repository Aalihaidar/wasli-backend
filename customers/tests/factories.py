"""Small helpers that build valid customer rows for tests (invented data only)."""

from customers.models import Customer
from users.models import User

PASSWORD = "s3cret-pass-4-tests"


def make_customer(
    email: str = "sara@example.com", name: str = "Sara Example"
) -> Customer:
    user = User.objects.create_user(None, PASSWORD, email=email, full_name=name)
    return Customer.objects.create(user=user, display_name=name)
