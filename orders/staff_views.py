"""The restaurant screen's orders (``/api/v1/staff/orders``): the polling list, accept, reject and
the Ready step."""

from uuid import UUID

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import Permission
from restaurants.permissions import get_membership, require_permission
from restaurants.services import mark_screen_online

from .services import (
    accept_order,
    mark_order_ready,
    orders_changed_since,
    reject_order,
)
from .staff_serializers import (
    StaffAcceptSerializer,
    StaffOrderListSerializer,
    StaffOrderSerializer,
    StaffOrdersQuerySerializer,
    StaffRejectSerializer,
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


class StaffOrderAcceptView(APIView):  # type: ignore[misc]
    permission_classes = [  # noqa: RUF012
        IsAuthenticated,
        require_permission(Permission.ORDERS_DECIDE),
    ]

    @extend_schema(
        operation_id="staff_orders_accept",
        tags=["staff"],
        summary="Accept an order",
        description=(
            "Accepts a placed order of the member's restaurant and promises a wait of 5, 10 or "
            "15 minutes (`400 invalid_choice` on `eta_minutes` for any other value). The answer "
            "is posted into the customer's chat as a `result` message in the same step. An "
            "order that is not waiting for an answer any more (another screen answered it, or "
            "it was answered before) is `409 order_invalid_transition`: poll the list to see "
            "its real state. An order of another restaurant, or an unknown id, is `404`. "
            "Answers with the updated order. Needs `orders.decide`."
        ),
        request=StaffAcceptSerializer,
        responses={200: StaffOrderSerializer},
    )
    def post(self, request: Request, id: UUID) -> Response:
        serializer = StaffAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = get_membership(request)
        order = accept_order(
            order_id=id,
            restaurant=membership.restaurant,
            actor=membership.user,
            eta_minutes=serializer.validated_data["eta_minutes"],
        )
        return Response(StaffOrderSerializer(order, context={"request": request}).data)


class StaffOrderRejectView(APIView):  # type: ignore[misc]
    permission_classes = [  # noqa: RUF012
        IsAuthenticated,
        require_permission(Permission.ORDERS_DECIDE),
    ]

    @extend_schema(
        operation_id="staff_orders_reject",
        tags=["staff"],
        summary="Reject an order",
        description=(
            "Rejects a placed order of the member's restaurant with a reason and an optional "
            "note of at most 200 characters; the note is required for `other` (`400 required` "
            "on `note`). The answer is posted into the customer's chat as a `result` message "
            "in the same step. An order that is not waiting for an answer any more is `409 "
            "order_invalid_transition`; an order of another restaurant, or an unknown id, is "
            "`404`. Answers with the updated order. Needs `orders.decide`."
        ),
        request=StaffRejectSerializer,
        responses={200: StaffOrderSerializer},
    )
    def post(self, request: Request, id: UUID) -> Response:
        serializer = StaffRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = get_membership(request)
        order = reject_order(
            order_id=id,
            restaurant=membership.restaurant,
            actor=membership.user,
            reason_code=serializer.validated_data["reason_code"],
            note=serializer.validated_data.get("note", ""),
        )
        return Response(StaffOrderSerializer(order, context={"request": request}).data)


class StaffOrderReadyView(APIView):  # type: ignore[misc]
    permission_classes = [  # noqa: RUF012
        IsAuthenticated,
        require_permission(Permission.ORDERS_DECIDE),
    ]

    @extend_schema(
        operation_id="staff_orders_ready",
        tags=["staff"],
        summary="Mark an accepted order as ready",
        description=(
            "Says that an accepted order of the member's restaurant is ready and on its way to "
            "the car. There is no body. The customer's chat gets a `result` message with "
            "`status: ready` in the same step. Only an accepted order can become ready: a "
            "placed, rejected or already ready order is `409 order_invalid_transition` (poll "
            "the list to see its real state). An order of another restaurant, or an unknown "
            "id, is `404`. Answers with the updated order. Needs `orders.decide`."
        ),
        request=None,
        responses={200: StaffOrderSerializer},
    )
    def post(self, request: Request, id: UUID) -> Response:
        membership = get_membership(request)
        order = mark_order_ready(
            order_id=id, restaurant=membership.restaurant, actor=membership.user
        )
        return Response(StaffOrderSerializer(order, context={"request": request}).data)
