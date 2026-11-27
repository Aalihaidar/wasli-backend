from django.urls import path

from . import staff_views, views

urlpatterns = [
    path("orders/<uuid:id>", views.OrderDetailView.as_view(), name="orders-detail"),
    path(
        "staff/orders",
        staff_views.StaffOrderListView.as_view(),
        name="staff-orders",
    ),
    path(
        "staff/orders/<uuid:id>/accept",
        staff_views.StaffOrderAcceptView.as_view(),
        name="staff-orders-accept",
    ),
    path(
        "staff/orders/<uuid:id>/reject",
        staff_views.StaffOrderRejectView.as_view(),
        name="staff-orders-reject",
    ),
    path(
        "staff/orders/<uuid:id>/ready",
        staff_views.StaffOrderReadyView.as_view(),
        name="staff-orders-ready",
    ),
]
