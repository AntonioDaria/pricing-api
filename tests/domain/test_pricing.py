"""Tests for lowest-price selection."""

from app.domain.models import RateOption
from app.domain.pricing import lowest_price


def test_returns_minimum_of_matching_options() -> None:
    """The lowest price_value among the surviving options is returned."""
    prices = [
        RateOption(price_value=150.0, currency="EUR", is_cancellable=True),
        RateOption(price_value=99.5, currency="EUR", is_cancellable=True),
        RateOption(price_value=120.0, currency="EUR", is_cancellable=True),
    ]

    assert lowest_price(prices, currency="EUR", cancellable=True) == 99.5


def test_excludes_options_in_another_currency() -> None:
    """A cheaper option in a different currency can never win."""
    prices = [
        RateOption(price_value=10.0, currency="USD", is_cancellable=True),
        RateOption(price_value=120.0, currency="EUR", is_cancellable=True),
    ]

    assert lowest_price(prices, currency="EUR", cancellable=True) == 120.0


def test_cancellable_true_excludes_non_cancellable_options() -> None:
    """A cheaper non-cancellable option is dropped when cancellable is requested."""
    prices = [
        RateOption(price_value=80.0, currency="EUR", is_cancellable=False),
        RateOption(price_value=130.0, currency="EUR", is_cancellable=True),
    ]

    assert lowest_price(prices, currency="EUR", cancellable=True) == 130.0


def test_cancellable_true_returns_none_when_no_cancellable_options() -> None:
    """Requesting cancellable prices with none available yields None."""
    prices = [RateOption(price_value=80.0, currency="EUR", is_cancellable=False)]

    assert lowest_price(prices, currency="EUR", cancellable=True) is None


def test_cancellable_false_keeps_all_options() -> None:
    """With cancellable False no cancellability filter is applied."""
    prices = [
        RateOption(price_value=80.0, currency="EUR", is_cancellable=False),
        RateOption(price_value=130.0, currency="EUR", is_cancellable=True),
    ]

    assert lowest_price(prices, currency="EUR", cancellable=False) == 80.0


def test_empty_input_returns_none() -> None:
    """No options at all yields None."""
    assert lowest_price([], currency="EUR", cancellable=True) is None
