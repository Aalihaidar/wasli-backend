from django.urls import path

from . import views

urlpatterns = [
    path("orders/<uuid:id>", views.OrderDetailView.as_view(), name="orders-detail"),
]
