"""In-memory Cache adapter: a dict of values with optional TTL expiry."""

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

import structlog

logger = structlog.get_logger(__name__)


class InMemoryCache:
    """A Cache holding values in a dict, expiring them against an injectable clock."""

    def __init__(self, time_fn: Callable[[], float] = time.monotonic) -> None:
        """Create an empty cache reading the current time from `time_fn`."""
        self._time_fn = time_fn
        self._entries: dict[str, tuple[object, float | None]] = {}

    def get(self, key: str) -> object | None:
        """Return the cached value, or None if the key is missing or expired."""
        entry = self._entries.get(key)
        if entry is None:
            return None # cache miss

        value, expires_at = entry
        if expires_at is not None and self._time_fn() >= expires_at:
            del self._entries[key]
            return None
        return value

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        """Cache a value under a key for `ttl` seconds, or indefinitely when ttl is None."""
        expires_at = None if ttl is None else self._time_fn() + ttl
        self._entries[key] = (value, expires_at)


if TYPE_CHECKING:
    from app.services.ports import Cache

    _cache_conforms: Cache = InMemoryCache()
