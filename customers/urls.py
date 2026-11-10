from django.urls import path

from . import views

urlpatterns = [
    path("customers/signup", views.SignupView.as_view(), name="customers-signup"),
    path("customers/verify", views.VerifyView.as_view(), name="customers-verify"),
    path(
        "customers/resend-code",
        views.ResendCodeView.as_view(),
        name="customers-resend-code",
    ),
    path("customers/login", views.LoginView.as_view(), name="customers-login"),
    path("customers/logout", views.LogoutView.as_view(), name="customers-logout"),
    path("customers/me", views.MeView.as_view(), name="customers-me"),
    path("customers/me/contact", views.ContactView.as_view(), name="customers-contact"),
    path(
        "customers/me/contact/verify",
        views.ContactVerifyView.as_view(),
        name="customers-contact-verify",
    ),
    path(
        "customers/password-reset",
        views.PasswordResetView.as_view(),
        name="customers-password-reset",
    ),
    path(
        "customers/password-reset/confirm",
        views.PasswordResetConfirmView.as_view(),
        name="customers-password-reset-confirm",
    ),
]
