from django.urls import path

from . import staff_views, views

urlpatterns = [
    path("orders/<uuid:id>", views.OrderDetailView.as_view(), name="orders-detail"),
    path(
        "staff/orders",
        staff_views.StaffOrderListView.as_view(),
        name="staff-orders",
    ),
]
