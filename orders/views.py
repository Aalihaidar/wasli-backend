"""The customer's own order (``GET /api/v1/orders/{id}``)."""

import uuid

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from customers.permissions import get_customer
from customers.views import CustomerView

from .models import Order
from .serializers import OrderSerializer


class OrderDetailView(CustomerView):
    @extend_schema(
        operation_id="orders_retrieve",
        tags=["orders"],
        summary="Read your own order",
        description=(
            "The order the customer placed: its number, `status`, `order_type`, when it was "
            "placed, the wait the restaurant gave (`eta_minutes`) or the reason and note of a "
            "rejection, and the totals in fils. The app polls it, or reads the `result` message "
            "in the chat. Another customer's order, or an unknown id, is a `404`."
        ),
        responses={200: OrderSerializer},
    )
    def get(self, request: Request, id: uuid.UUID) -> Response:
        order = get_object_or_404(Order, pk=id, customer=get_customer(request))
        return Response(OrderSerializer(order).data)
