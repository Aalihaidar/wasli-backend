"""Where each uploaded image is stored (ADR 0023).

Every image of a restaurant lives under one folder, laid out like the admin: names are lowercase
kebab case made from the English name, and a category's own picture sits one level above its folder.

```text
restaurants/<slug>/logo/logo.png
restaurants/<slug>/cover/cover.jpg
restaurants/<slug>/menu-images/<caption>.jpg
restaurants/<slug>/menu/<category>.webp                 the picture of a category
restaurants/<slug>/menu/<category>/<item>.webp          an item of that category
restaurants/<slug>/menu/<category>/<sub>.webp           the picture of a subcategory
restaurants/<slug>/menu/<category>/<sub>/<item>.webp    an item of the subcategory, and so on
```

The functions are the ``upload_to`` of each image field. They only build a name; the storage adds
a short random suffix when the name is taken (a stored file is never overwritten, because files are
cached for a year). A rename moves the files afterwards (``core/media_sync.py``), and
``python manage.py organize_media`` moves everything on demand.
"""

import re
from pathlib import PurePosixPath
from typing import Any

from django.utils.text import slugify

# The longest part of a name kept in a folder or file name, so a stored name always fits the
# 300 characters of the image columns (three category levels, an item and a suffix).
MAX_FOLDER_CHARS = 40
MAX_FILE_CHARS = 60
MAX_EXTENSION_CHARS = 5

RESTAURANTS_FOLDER = "restaurants"

# The length of the image columns: a deep path with a suffix still fits.
IMAGE_NAME_LENGTH = 300


def kebab(text: str | None, fallback: str, limit: int = MAX_FOLDER_CHARS) -> str:
    """Lowercase kebab case of ``text`` (letters and digits of the English alphabet only), cut at
    ``limit`` characters; ``fallback`` when nothing is left (an Arabic-only or empty name)."""
    cleaned = slugify(re.sub(r"[_\s]+", " ", text or ""))
    return cleaned[:limit].strip("-") or fallback


def extension(filename: str) -> str:
    """The lowercase extension of ``filename`` with its dot (``.webp``), or an empty string."""
    suffix = PurePosixPath(filename).suffix.lower()
    return suffix if 1 < len(suffix) <= MAX_EXTENSION_CHARS else ""


def restaurant_folder(slug: str) -> str:
    return f"{RESTAURANTS_FOLDER}/{slug}"


def category_folders(category: Any) -> list[str]:
    """The folder names from the top category down to ``category`` itself."""
    return [kebab(node.name_en, "category") for node in category.lineage()]


def logo_path(instance: Any, filename: str) -> str:
    return f"{restaurant_folder(instance.slug)}/logo/logo{extension(filename)}"


def cover_path(instance: Any, filename: str) -> str:
    return f"{restaurant_folder(instance.slug)}/cover/cover{extension(filename)}"


def menu_image_path(instance: Any, filename: str) -> str:
    stem = kebab(instance.caption_en, "menu-image", MAX_FILE_CHARS)
    return f"{restaurant_folder(instance.restaurant.slug)}/menu-images/{stem}{extension(filename)}"


def category_image_path(instance: Any, filename: str) -> str:
    """The picture of a category, one level above the folder of that category."""
    *parents, own = category_folders(instance)
    folder = "/".join([restaurant_folder(instance.restaurant.slug), "menu", *parents])
    return f"{folder}/{own}{extension(filename)}"


def item_image_path(instance: Any, filename: str) -> str:
    folders = category_folders(instance.category)
    folder = "/".join(
        [restaurant_folder(instance.category.restaurant.slug), "menu", *folders]
    )
    stem = kebab(instance.name_en, "item", MAX_FILE_CHARS)
    return f"{folder}/{stem}{extension(filename)}"
