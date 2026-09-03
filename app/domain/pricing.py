"""Lowest-price selection: filter a reading's rate options, then take the minimum."""

from collections.abc import Iterable

from app.domain.models import RateOption


def lowest_price(
    prices: Iterable[RateOption],
    currency: str,
    cancellable: bool,
) -> float | None:
    """Return the lowest price_value in `currency`, keeping only cancellable options if asked.

    Returns None when no option survives the filters.
    """
    matching = [
        option.price_value
        for option in prices
        if option.currency == currency and (option.is_cancellable or not cancellable)
    ]
    return min(matching) if matching else None
