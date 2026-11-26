"""The restaurant screen's orders (``/api/v1/staff/orders``). Accept and reject come next."""

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import Permission
from restaurants.permissions import get_membership, require_permission
from restaurants.services import mark_screen_online

from .services import orders_changed_since
from .staff_serializers import (
    StaffOrderListSerializer,
    StaffOrdersQuerySerializer,
)


class StaffOrderListView(APIView):  # type: ignore[misc]
    """Polling list: it keeps its own shape and is not paginated (docs/api-conventions.md)."""

    permission_classes = [  # noqa: RUF012
        IsAuthenticated,
        require_permission(Permission.ORDERS_VIEW),
    ]

    @extend_schema(
        operation_id="staff_orders_list",
        tags=["staff"],
        summary="List the restaurant's orders that are new or changed",
        description=(
            "The signed-in member's restaurant's orders created or changed after `since` "
            "(by default in the last 24 hours), newest first, each with its lines in both "
            "languages, the car, the optional position (`customer_location`, absent when the "
            "customer did not share it), `distance_m` and `distance_band`. Send the "
            "`server_time` of the answer back as `since` on the next call; the server reads "
            "from a few seconds before it, so a change is never missed and an order can "
            "arrive again unchanged: merge by `id` and keep the one with the latest "
            "`updated_at`. Every successful call marks the restaurant's screen online for "
            "customers (they see it as open while it polled in the last 60 seconds). This "
            "list is polled and is not paginated. Needs `orders.view`."
        ),
        parameters=[StaffOrdersQuerySerializer],
        responses={200: StaffOrderListSerializer},
    )
    def get(self, request: Request) -> Response:
        query = StaffOrdersQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        restaurant = get_membership(request).restaurant
        # Taken before the read, so nothing that changes during it is skipped by the next call.
        now = timezone.now()
        orders = orders_changed_since(
            restaurant, query.validated_data.get("since"), now
        )
        body = StaffOrderListSerializer(
            {"server_time": now, "orders": orders}, context={"request": request}
        ).data
        mark_screen_online(restaurant, now)
        return Response(body)
