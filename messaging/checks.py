from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error, Tags, register


@register(Tags.security)
def check_outbox_not_in_production(
    app_configs: Any, **kwargs: Any
) -> list[CheckMessage]:
    """Keep the outbox out of production, at every start and in the deploy check.

    The outbox stores verification codes in readable form. Production uses
    ``MESSAGING_BACKEND=disabled`` until a real backend exists.
    """
    if settings.ENVIRONMENT == "production" and settings.MESSAGING_BACKEND == "outbox":
        return [
            Error(
                "The outbox messaging backend is configured in production.",
                hint=(
                    "Set MESSAGING_BACKEND to a real backend, or to 'disabled' until one "
                    "exists; the outbox is for local and staging only."
                ),
                id="messaging.E001",
            )
        ]
    return []
