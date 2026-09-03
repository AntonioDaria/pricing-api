"""Typed domain errors raised by the application and mapped to HTTP responses."""


class StoreUnavailableError(Exception):
    """Raised when the pricing store backend is unreachable, timing out or erroring."""
