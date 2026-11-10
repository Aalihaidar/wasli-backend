import urllib.request
import uuid
from typing import Any

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

USER_AGENT = "wasli-check-media/1.0"


class Command(BaseCommand):
    help = (
        "Check the image storage: write a small file, print its public URL, read it back over "
        "HTTP (with --fetch) and delete it. Use it after setting up the R2 bucket."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--fetch",
            action="store_true",
            help="Also download the file from its public URL (needs the network).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        name = f"healthcheck/{uuid.uuid4()}.txt"
        body = b"wasli storage check"
        saved = default_storage.save(name, ContentFile(body))
        try:
            url = default_storage.url(saved)
            self.stdout.write(f"Stored {saved}")
            self.stdout.write(f"Public URL: {url}")
            if options["fetch"]:
                self._fetch(url, body)
        finally:
            default_storage.delete(saved)
        self.stdout.write(self.style.SUCCESS("The image storage works."))

    def _fetch(self, url: str, expected: bytes) -> None:
        if not url.startswith("https://"):
            raise CommandError(f"The public URL is not an https address: {url}")
        # Cloudflare answers 403 to Python's default User-Agent on a public address, so name ourselves.
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
        try:
            with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
                got = response.read()
        except OSError as error:
            raise CommandError(
                f"The file was stored but cannot be read from its public URL: {error}. "
                "Is the public access (r2.dev address) enabled on the bucket?"
            ) from error
        if got != expected:
            raise CommandError(
                "The file read from the public URL is not the one stored."
            )
        self.stdout.write("Read back over HTTP: ok")
