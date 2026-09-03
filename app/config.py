"""Application configuration, read from the environment."""

import os
from dataclasses import dataclass

CURRENT_PRICE_TTL_ENV_VAR = "CURRENT_PRICE_TTL_SECONDS"
DEFAULT_CURRENT_PRICE_TTL_SECONDS = 6 * 60 * 60


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the service."""

    current_price_ttl_seconds: int


def get_settings() -> Settings:
    """Build the settings from the environment, falling back to the documented defaults."""
    return Settings(
        current_price_ttl_seconds=_positive_int_from_env(
            CURRENT_PRICE_TTL_ENV_VAR, DEFAULT_CURRENT_PRICE_TTL_SECONDS
        ),
    )


def _positive_int_from_env(name: str, default: int) -> int:
    """Read a positive integer from the environment, or return the default when the var is unset.

    Raises ValueError if the variable is set to something that is not a positive integer.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer, got {raw!r}")
    return value
