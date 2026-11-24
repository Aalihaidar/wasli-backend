"""Keep every stored image where the folder layout says (ADR 0023).

``organize()`` finds the images that are not at the path ``core/media_paths.py`` gives them and
moves each one: it copies the file to its new name, points the database row (and the chat messages
that name the same file) at it, and only then deletes the old file, so a failure never leaves a
row without its image. It is idempotent: a file already in place is left alone.

It runs in two ways: by hand for every restaurant (``python manage.py organize_media``), and
automatically after a change that can move a file (renaming or re-slugging a restaurant, renaming
or moving a category, renaming an item, a changed caption). The automatic run happens once the
change is committed, only for the restaurant concerned, and never makes the save fail: if the
storage is down, the file stays where it was and the command repairs it later.
"""

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import models, transaction
from django.db.models.signals import post_save

from chat.models import Message
from core.media_paths import (
    category_image_path,
    cover_path,
    item_image_path,
    logo_path,
    menu_image_path,
)
from menu.models import MenuCategory, MenuItem
from restaurants.models import Restaurant, RestaurantMenuImage

logger = logging.getLogger("core.media")

# (model, image field, the path builder of that field)
_FIELDS: tuple[tuple[type[models.Model], str, Callable[[Any, str], str]], ...] = (
    (Restaurant, "logo", logo_path),
    (Restaurant, "cover", cover_path),
    (RestaurantMenuImage, "image", menu_image_path),
    (MenuCategory, "image", category_image_path),
    (MenuItem, "image", item_image_path),
)

# The fields whose change can move a file. A save that lists ``update_fields`` without any of them
# (the order number, the heartbeat) cannot, so it does not look at the storage at all.
_AFFECTING: dict[type[models.Model], frozenset[str]] = {
    Restaurant: frozenset({"slug", "name_en", "logo", "cover"}),
    RestaurantMenuImage: frozenset(
        {"caption_en", "image", "restaurant", "restaurant_id"}
    ),
    MenuCategory: frozenset({"name_en", "parent", "parent_id", "image"}),
    MenuItem: frozenset({"name_en", "category", "category_id", "image"}),
}


@dataclass(frozen=True)
class Move:
    model: type[models.Model]
    field: str
    pk: Any
    old: str
    target: str


def is_in_place(current: str, target: str) -> bool:
    """Whether ``current`` already is ``target``, allowing the random suffix the storage adds
    when a name was taken (``chicken-burger_k3j9d2.webp``)."""
    now, want = PurePosixPath(current), PurePosixPath(target)
    return (
        now.parent == want.parent
        and now.suffix == want.suffix
        and (now.stem == want.stem or now.stem.startswith(f"{want.stem}_"))
    )


def plan(restaurant_id: Any = None) -> Iterator[Move]:
    """Every stored image that is not where the layout says (of one restaurant, or of all)."""
    for model, field, builder in _FIELDS:
        rows = model._default_manager.exclude(**{field: ""})
        if restaurant_id is not None:
            key = "pk" if model is Restaurant else "restaurant_id"
            rows = rows.filter(**{key: restaurant_id})
        for obj in rows.iterator():
            current: str = getattr(obj, field).name
            target = builder(obj, PurePosixPath(current).name)
            if not is_in_place(current, target):
                yield Move(model, field, obj.pk, current, target)


def _still_used(name: str) -> bool:
    """Whether any row still names the file (rows that share one file keep it alive)."""
    return any(
        model._default_manager.filter(**{field: name}).exists()
        for model, field, _ in _FIELDS
    )


def apply(move: Move) -> str:
    """Move one file and return its final name. The old file goes last, and only when no row
    names it any more."""
    with default_storage.open(move.old, "rb") as source:
        data = source.read()
    final = default_storage.save(move.target, ContentFile(data))
    with transaction.atomic():
        move.model._default_manager.filter(pk=move.pk).update(**{move.field: final})
        # The welcome's picture messages name the same file as the menu image.
        Message.objects.filter(image=move.old).update(image=final)
    if not _still_used(move.old):
        default_storage.delete(move.old)
    return final


def organize(restaurant_id: Any = None) -> list[tuple[str, str]]:
    """Move every image that is out of place; returns the ``(old, new)`` names moved. A row whose
    file is missing from the storage is left as it is."""
    moved: list[tuple[str, str]] = []
    for move in plan(restaurant_id):
        if not default_storage.exists(move.old):
            logger.warning("Image missing from the storage: %s", move.old)
            continue
        moved.append((move.old, apply(move)))
    return moved


def _restaurant_of(instance: models.Model) -> Any:
    return instance.pk if isinstance(instance, Restaurant) else instance.restaurant_id  # type: ignore[attr-defined]


def _run_after_commit(restaurant_id: Any) -> None:
    try:
        organize(restaurant_id)
    except Exception:
        # The save is already committed and must not fail because the storage did. The files stay
        # where they were and ``manage.py organize_media`` moves them later.
        logger.exception("Could not move the images of restaurant %s", restaurant_id)


def _on_saved(
    sender: type[models.Model],
    instance: models.Model,
    created: bool,
    raw: bool = False,
    update_fields: Any = None,
    **kwargs: Any,
) -> None:
    """A new row was uploaded to its place already, and a save of other fields cannot move a
    file: only a change of a name, a parent or a slug can."""
    if created or raw:
        return
    if update_fields is not None and not (set(update_fields) & _AFFECTING[sender]):
        return
    restaurant_id = _restaurant_of(instance)
    transaction.on_commit(lambda: _run_after_commit(restaurant_id))


def connect() -> None:
    """Move the files of a restaurant after a change that can rename their folders."""
    for model in _AFFECTING:
        post_save.connect(
            _on_saved,
            sender=model,
            weak=False,
            dispatch_uid=f"core.media_sync.{model.__name__}",
        )
