from collections.abc import Iterator

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    """Start every test with an empty cache.

    The request throttles count in the cache. Without this, a test that exhausts a throttle
    (several requests from one address) makes later tests in the same minute fail with 429.
    """
    cache.clear()
    yield
