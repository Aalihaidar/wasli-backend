from django.apps import AppConfig


class MessagingConfig(AppConfig):
    name = "messaging"

    def ready(self) -> None:
        # Registers the system check that keeps the outbox out of production.
        from . import checks  # noqa: F401
