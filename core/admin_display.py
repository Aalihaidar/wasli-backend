"""Small pieces the admin classes share: an image thumbnail and a coloured label.

They return markup with CSS classes only (``static/admin/css/wasli.css``), never inline styles,
so the pages keep working when the Content Security Policy is enforced.
"""

from typing import Literal

from django.db.models.fields.files import FieldFile
from django.utils.html import format_html
from django.utils.safestring import SafeString

BadgeKind = Literal["ok", "warn", "bad", "info", "muted"]


def thumbnail(image: FieldFile | None, *, large: bool = False) -> SafeString:
    """The image as a small picture, or a dash when there is none."""
    if not image:
        return format_html('<span class="wasli-empty">{}</span>', "—")
    size = "wasli-thumb wasli-thumb--large" if large else "wasli-thumb"
    return format_html(
        '<img src="{}" alt="" class="{}" loading="lazy">', image.url, size
    )


def badge(text: str, kind: BadgeKind) -> SafeString:
    """A short coloured label for a status."""
    return format_html(
        '<span class="wasli-badge wasli-badge--{}">{}</span>', kind, text
    )
