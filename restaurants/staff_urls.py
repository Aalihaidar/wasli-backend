from django.urls import path

from .staff_views import (
    StaffLoginView,
    StaffLogoutView,
    StaffMeView,
    StaffPasswordView,
)

urlpatterns = [
    path("auth/login", StaffLoginView.as_view(), name="staff-login"),
    path("auth/logout", StaffLogoutView.as_view(), name="staff-logout"),
    path("auth/password", StaffPasswordView.as_view(), name="staff-password"),
    path("staff/me", StaffMeView.as_view(), name="staff-me"),
]
