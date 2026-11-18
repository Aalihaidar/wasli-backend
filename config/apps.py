from django.contrib.admin.apps import AdminConfig


class WasliAdminConfig(AdminConfig):
    """Makes ``config.admin.WasliAdminSite`` the default admin site (the documented way to
    replace Django's: it is listed in INSTALLED_APPS instead of ``django.contrib.admin``)."""

    default_site = "config.admin.WasliAdminSite"
