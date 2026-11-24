from collections.abc import Iterator

import pytest
from django.core.cache import cache
from django.core.files.storage import InMemoryStorage, Storage, storages


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    """Start every test with an empty cache.

    The request throttles count in the cache. Without this, a test that exhausts a throttle
    (several requests from one address) makes later tests in the same minute fail with 429.
    """
    cache.clear()
    yield


def _delete_all(storage: Storage, folder: str = "") -> None:
    """Delete every file below ``folder`` with the storage's own API."""
    directories, files = storage.listdir(folder)
    for name in files:
        storage.delete(f"{folder}/{name}".lstrip("/"))
    for directory in directories:
        _delete_all(storage, f"{folder}/{directory}".lstrip("/"))


@pytest.fixture(autouse=True)
def _empty_media_storage() -> Iterator[None]:
    """Start every test with an empty image storage.

    Tests keep uploaded images in memory for the whole run. A name taken by an earlier test would
    make the storage add its random suffix to the next upload of the same name, and a test that
    checks where a file is stored would fail depending on the order of the tests.
    """
    storage = storages["default"]
    if isinstance(storage, InMemoryStorage):
        _delete_all(storage)
    yield
