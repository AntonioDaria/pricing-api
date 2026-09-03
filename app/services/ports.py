"""Ports: the Protocols the services layer depends on, implemented by adapters."""

from collections.abc import Iterable
from typing import Protocol

from app.domain.models import Reading

HotelArrival = tuple[int, int]
"""A (hotel_id, arrival_date) pair, with arrival_date as days-since-epoch."""


class PricingStore(Protocol):
    """Read access to the pricing key-value store."""

    def get_latest_readings(self, pairs: Iterable[HotelArrival]) -> dict[HotelArrival, Reading]:
        """Return the newest reading (max extract_date) per pair, omitting pairs with no data.

        Raises StoreUnavailableError if the backend is unavailable.
        """
        ...


class Cache(Protocol):
    """A simple key-value cache with optional per-entry expiry."""

    def get(self, key: str) -> object | None:
        """Return the cached value, or None if the key is missing or expired."""
        ...

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        """Cache a value under a key for `ttl` seconds, or indefinitely when ttl is None."""
        ...
