from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Tags, Warning, register


@register(Tags.security)
def check_media_storage_is_durable(
    app_configs: Any, **kwargs: Any
) -> list[CheckMessage]:
    """Warn when staging or production keeps uploaded images on the local disk.

    Those services run on an ephemeral disk, so every image uploaded in the admin would
    disappear at the next deploy. Local development may use the disk.
    """
    if settings.ENVIRONMENT != "local" and settings.MEDIA_STORAGE == "filesystem":
        return [
            Warning(
                f"Uploaded images are kept on the local disk while ENVIRONMENT is "
                f"{settings.ENVIRONMENT!r}.",
                hint="Set MEDIA_STORAGE=r2 and the R2_* settings: the disk is erased at every deploy.",
                id="core.W001",
            )
        ]
    return []
