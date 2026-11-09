import pytest
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from customers.authentication import CustomerTokenAuthentication
from customers.permissions import IsCustomer, get_customer
from customers.services import revoke_session, start_session
from customers.tests.factories import make_customer
from restaurants.tests.factories import make_user

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


class CustomerView(APIView):  # type: ignore[misc]
    authentication_classes = [CustomerTokenAuthentication]  # noqa: RUF012
    permission_classes = [IsCustomer]  # noqa: RUF012

    def get(self, request: Request) -> Response:
        return Response({"customer": str(get_customer(request).pk)})


class MixedView(APIView):  # type: ignore[misc]
    """Both token kinds accepted, but only a customer token passes IsCustomer."""

    authentication_classes = [CustomerTokenAuthentication]  # noqa: RUF012
    permission_classes = [IsAuthenticated]  # noqa: RUF012

    def get(self, request: Request) -> Response:
        return Response({"user": str(request.user.pk)})


class StaffView(APIView):  # type: ignore[misc]
    """Default authentication (staff tokens) and default permission (signed in)."""

    def get(self, request: Request) -> Response:
        return Response({"user": str(request.user.pk)})


class OpenView(APIView):  # type: ignore[misc]
    authentication_classes = [CustomerTokenAuthentication]  # noqa: RUF012
    permission_classes = [AllowAny]  # noqa: RUF012

    def get(self, request: Request) -> Response:
        return Response({"signed_in": request.user.is_authenticated})


def get(view: type[APIView], authorization: str | None = None) -> Response:
    extra = {"HTTP_AUTHORIZATION": authorization} if authorization else {}
    return view.as_view()(factory.get("/x/", **extra))


class TestCustomerToken:
    def test_a_valid_token_signs_the_customer_in(self) -> None:
        customer = make_customer()
        _, token = start_session(customer)

        response = get(CustomerView, f"Customer {token}")

        assert response.status_code == 200
        assert response.data == {"customer": str(customer.pk)}

    def test_the_keyword_is_case_insensitive(self) -> None:
        _, token = start_session(make_customer())

        assert get(CustomerView, f"customer {token}").status_code == 200

    def test_request_user_is_the_customers_user(self) -> None:
        customer = make_customer()
        _, token = start_session(customer)

        response = get(MixedView, f"Customer {token}")

        assert response.data == {"user": str(customer.user.pk)}

    @pytest.mark.parametrize(
        "header", ["Customer", "Customer a b", "Customer not-a-real-token"]
    )
    def test_a_bad_token_is_refused_with_401(self, header: str) -> None:
        response = get(CustomerView, header)

        assert response.status_code == 401
        assert response["WWW-Authenticate"] == "Customer"

    def test_a_revoked_token_is_refused(self) -> None:
        session, token = start_session(make_customer())
        revoke_session(session)

        assert get(CustomerView, f"Customer {token}").status_code == 401

    def test_a_deactivated_account_is_refused(self) -> None:
        customer = make_customer()
        _, token = start_session(customer)
        customer.user.is_active = False
        customer.user.save()

        assert get(CustomerView, f"Customer {token}").status_code == 401

    def test_no_header_is_unauthenticated(self) -> None:
        assert get(CustomerView).status_code == 401

    def test_an_open_endpoint_accepts_no_token(self) -> None:
        response = get(OpenView)

        assert response.status_code == 200
        assert response.data == {"signed_in": False}

    def test_a_bad_token_is_refused_even_on_an_open_endpoint(self) -> None:
        assert get(OpenView, "Customer wrong").status_code == 401

    def test_using_the_token_refreshes_last_seen_only_when_stale(self) -> None:
        session, token = start_session(make_customer())
        seen = session.last_seen_at

        get(CustomerView, f"Customer {token}")

        session.refresh_from_db()
        assert session.last_seen_at == seen  # seen a moment ago, so not rewritten


class TestIsolationBetweenTokenKinds:
    def test_a_customer_token_does_not_open_a_staff_endpoint(self) -> None:
        _, token = start_session(make_customer())

        assert get(StaffView, f"Customer {token}").status_code == 401

    def test_a_staff_token_does_not_open_a_customer_endpoint(self) -> None:
        staff_token = Token.objects.create(user=make_user("clerk"))

        assert get(CustomerView, f"Token {staff_token.key}").status_code == 401

    def test_the_staff_endpoint_still_accepts_a_staff_token(self) -> None:
        user = make_user("clerk")
        staff_token = Token.objects.create(user=user)

        response = get(StaffView, f"Token {staff_token.key}")

        assert response.status_code == 200
        assert response.data == {"user": str(user.pk)}

    def test_is_customer_refuses_a_request_without_a_customer_session(self) -> None:
        request = factory.get("/x/")
        request.auth = None

        assert IsCustomer().has_permission(request, None) is False
