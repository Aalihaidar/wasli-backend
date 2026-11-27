"""Reading a voice clip without ever writing it to the disk.

Django keeps a small upload in memory and writes a larger one (over ``FILE_UPLOAD_MAX_MEMORY_SIZE``,
2.5 MB) to a temporary file. A voice clip may be up to 5 MB, and a handler that only keeps files in
memory silently drops anything above that threshold. This handler always keeps the file in memory.
It is used by the voice endpoint only (the Django admin keeps Django's default handlers for its
images), and the request is already capped at 6 MB before any view runs (``REQUEST_BODY_LIMITS``),
so the memory it can use is bounded.
"""

from typing import Any

from django.core.files.uploadhandler import MemoryFileUploadHandler


class AlwaysInMemoryUploadHandler(MemoryFileUploadHandler):
    def handle_raw_input(
        self,
        input_data: Any,
        META: Any,
        content_length: int,
        boundary: str,
        encoding: str | None = None,
    ) -> None:
        self.activated = True
