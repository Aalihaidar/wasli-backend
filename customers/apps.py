from django.apps import AppConfig


class CustomersConfig(AppConfig):
    name = "customers"

    def ready(self) -> None:
        # Registers the OpenAPI description of the customer token header.
        from . import schema  # noqa: F401
