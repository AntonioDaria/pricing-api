"""Tests for the in-memory Cache adapter."""

from app.adapters.in_memory_cache import InMemoryCache


class FakeClock:
    """A controllable monotonic clock for testing TTL expiry."""

    def __init__(self) -> None:
        """Start the clock at zero."""
        self.now = 0.0

    def __call__(self) -> float:
        """Return the current fake time."""
        return self.now

    def advance(self, seconds: float) -> None:
        """Move the fake clock forward."""
        self.now += seconds


def test_get_returns_a_value_that_was_set() -> None:
    """A cached value is returned on a hit."""
    cache = InMemoryCache(time_fn=FakeClock())
    cache.set("price:1", 506.0, ttl=60)

    assert cache.get("price:1") == 506.0


def test_get_returns_none_for_an_unknown_key() -> None:
    """An uncached key is a miss."""
    assert InMemoryCache(time_fn=FakeClock()).get("nope") is None


def test_value_expires_after_its_ttl() -> None:
    """A value is a miss once the clock passes its expiry."""
    clock = FakeClock()
    cache = InMemoryCache(time_fn=clock)
    cache.set("price:1", 506.0, ttl=60)

    clock.advance(59)
    assert cache.get("price:1") == 506.0

    clock.advance(1)
    assert cache.get("price:1") is None


def test_ttl_none_never_expires() -> None:
    """A value cached without a ttl survives an arbitrary amount of time."""
    clock = FakeClock()
    cache = InMemoryCache(time_fn=clock)
    cache.set("historic:1", 612.0)

    clock.advance(10_000_000)

    assert cache.get("historic:1") == 612.0


def test_set_overwrites_an_existing_key() -> None:
    """Setting a key again replaces the previous value."""
    cache = InMemoryCache(time_fn=FakeClock())
    cache.set("price:1", 506.0)
    cache.set("price:1", 489.0)

    assert cache.get("price:1") == 489.0
