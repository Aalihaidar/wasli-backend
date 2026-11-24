from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "core"

    def ready(self) -> None:
        # Registers the system check about where uploaded images are kept.
        from . import (
            checks,  # noqa: F401
            media_sync,
        )

        # Moves the files of a restaurant after a rename, so the folders always match the admin.
        media_sync.connect()
