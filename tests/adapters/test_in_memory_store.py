"""Tests for the in-memory PricingStore adapter."""

from app.domain.models import RateOption
from tests.seed import (
    SAMPLE_ARRIVAL_DATE,
    SAMPLE_CURRENCY,
    SAMPLE_HOTEL_ID,
    sample_reading,
    seeded_store,
)


def _option(price: float) -> list[RateOption]:
    """Build a one-option price list at the given price, for distinguishing readings."""
    return [RateOption(price_value=price, currency=SAMPLE_CURRENCY, is_cancellable=True)]


def test_returns_the_newest_reading_for_a_pair() -> None:
    """With several extract_dates for one (hotel, arrival), the newest reading wins."""
    store = seeded_store(
        [
            sample_reading(extract_date=19030, prices=_option(100.0)),
            sample_reading(extract_date=19038, prices=_option(300.0)),
            sample_reading(extract_date=19035, prices=_option(200.0)),
        ]
    )

    result = store.get_latest_readings([(SAMPLE_HOTEL_ID, SAMPLE_ARRIVAL_DATE)])

    reading = result[(SAMPLE_HOTEL_ID, SAMPLE_ARRIVAL_DATE)]
    assert reading.extract_date == 19038
    assert reading.prices[0].price_value == 300.0


def test_omits_pairs_with_no_data() -> None:
    """A pair the store knows nothing about is absent from the result rather than None."""
    store = seeded_store()

    result = store.get_latest_readings(
        [(SAMPLE_HOTEL_ID, SAMPLE_ARRIVAL_DATE), (999, SAMPLE_ARRIVAL_DATE)]
    )

    assert (999, SAMPLE_ARRIVAL_DATE) not in result
    assert set(result) == {(SAMPLE_HOTEL_ID, SAMPLE_ARRIVAL_DATE)}


def test_resolves_a_batch_of_pairs_in_one_call() -> None:
    """Several pairs are all resolved by a single get_latest_readings call."""
    store = seeded_store(
        [
            sample_reading(hotel_id=1, arrival_date=19054),
            sample_reading(hotel_id=1, arrival_date=19055),
            sample_reading(hotel_id=2, arrival_date=19054),
        ]
    )
    pairs = [(1, 19054), (1, 19055), (2, 19054)]

    result = store.get_latest_readings(pairs)

    assert set(result) == set(pairs)
    assert [r.hotel_id for r in result.values()] == [1, 1, 2]


def test_empty_pairs_returns_empty_result() -> None:
    """Asking for no pairs returns an empty mapping."""
    assert seeded_store().get_latest_readings([]) == {}
