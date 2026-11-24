"""Move every stored image to the folder layout of ``core/media_paths.py`` (ADR 0023).

Run it with ``--dry-run`` first: it prints each move and changes nothing. A real run copies the file
to its new name, points the database row (and the chat messages that name the same file) at the new
name, and only then deletes the old file, so a failure never leaves a row without its image. It can
be run again at any time: a file that is already in the right place is left alone.

The same moves also happen by themselves after a rename in the admin (``core/media_sync.py``); this
command moves the files uploaded before the layout existed and repairs a move that could not finish.
"""

from typing import Any

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from core import media_sync


class Command(BaseCommand):
    help = (
        "Move the stored images to the folder layout of each restaurant "
        "(restaurants/<slug>/logo, cover, menu-images and menu/...). Use --dry-run first."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the moves and change nothing.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run: bool = options["dry_run"]
        moved = missing = 0
        for move in media_sync.plan():
            if not default_storage.exists(move.old):
                missing += 1
                self.stdout.write(self.style.WARNING(f"MISSING  {move.old}"))
                continue
            moved += 1
            if dry_run:
                self.stdout.write(f"{move.old}  ->  {move.target}")
            else:
                self.stdout.write(f"{move.old}  ->  {media_sync.apply(move)}")

        verb = "would move" if dry_run else "moved"
        self.stdout.write(self.style.SUCCESS(f"{moved} image(s) {verb}."))
        if missing:
            self.stdout.write(
                self.style.WARNING(
                    f"{missing} row(s) name a file that is not in the storage; "
                    "they were left as they are."
                )
            )
