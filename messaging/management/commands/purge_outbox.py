from typing import Any

from django.core.management.base import BaseCommand

from messaging.backends import purge_old_messages


class Command(BaseCommand):
    help = "Delete outbox messages older than OUTBOX_RETENTION_HOURS."

    def handle(self, *args: Any, **options: Any) -> None:
        deleted = purge_old_messages()
        self.stdout.write(f"Deleted {deleted} outbox message(s).")
