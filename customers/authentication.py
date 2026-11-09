from rest_framework.authentication import (
    BaseAuthentication,
    get_authorization_header,
)
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from users.models import User

from .models import CustomerSession
from .services import get_active_session, touch_session


class CustomerTokenAuthentication(BaseAuthentication):  # type: ignore[misc]
    """``Authorization: Customer <token>``.

    ``request.user`` is the customer's ``User`` and ``request.auth`` is the
    ``CustomerSession``. Customer views list this class explicitly; it is not a default, so
    a customer token never opens a staff endpoint and a staff token never opens a customer
    one.
    """

    keyword = "Customer"

    def authenticate(self, request: Request) -> tuple[User, CustomerSession] | None:
        header = get_authorization_header(request).split()
        if not header or header[0].lower() != self.keyword.lower().encode():
            return None  # not ours: let another class try
        if len(header) != 2:
            raise AuthenticationFailed("Invalid token header.")
        try:
            token = header[1].decode()
        except UnicodeError:
            raise AuthenticationFailed("Invalid token header.") from None
        session = get_active_session(token)
        if session is None:
            raise AuthenticationFailed("Invalid or revoked token.")
        user = session.customer.user
        if not user.is_active:
            raise AuthenticationFailed("This account is deactivated.")
        touch_session(session)
        return user, session

    def authenticate_header(self, request: Request) -> str:
        return self.keyword
