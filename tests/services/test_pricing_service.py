"""Tests for the pricing service pipeline, driven through the ports only."""

from collections.abc import Iterable
from datetime import date

import pytest

from app.adapters.in_memory_cache import InMemoryCache
from app.domain.dates import date_to_epoch_days
from app.domain.models import PriceDifference, RateOption, Reading
from app.errors import StoreUnavailableError
from app.services.ports import HotelArrival, PricingStore
from app.services.pricing_service import PricingService
from tests.seed import sample_reading, seeded_store

HOTEL = 3173269
CURRENCY = "SGD"


class RecordingStore:
    """A PricingStore that records the pairs passed to each call before delegating."""

    def __init__(self, inner: PricingStore) -> None:
        """Wrap an existing store and start with an empty call log."""
        self._inner = inner
        self.calls: list[list[HotelArrival]] = []

    def get_latest_readings(self, pairs: Iterable[HotelArrival]) -> dict[HotelArrival, Reading]:
        """Record the requested pairs, then delegate to the wrapped store."""
        requested = list(pairs)
        self.calls.append(requested)
        return self._inner.get_latest_readings(requested)

    @property
    def requested_pairs(self) -> set[HotelArrival]:
        """Return every pair asked for across all calls."""
        return {pair for call in self.calls for pair in call}


class UnavailableStore:
    """A PricingStore standing in for a backend outage."""

    def get_latest_readings(self, pairs: Iterable[HotelArrival]) -> dict[HotelArrival, Reading]:
        """Raise StoreUnavailableError, as a real adapter would on an outage."""
        raise StoreUnavailableError("backend down")


class FakeClock:
    """A controllable monotonic clock for driving cache TTL expiry."""

    def __init__(self) -> None:
        """Start the clock at zero."""
        self.now = 0.0

    def __call__(self) -> float:
        """Return the current fake time."""
        return self.now

    def advance(self, seconds: float) -> None:
        """Move the fake clock forward."""
        self.now += seconds


def option(price: float, currency: str = CURRENCY, cancellable: bool = True) -> RateOption:
    """Build a single rate option for seeding readings."""
    return RateOption(price_value=price, currency=currency, is_cancellable=cancellable)


def reading_for(day: date, prices: list[RateOption], hotel: int = HOTEL) -> Reading:
    """Build a reading for a hotel's arrival date, using the sample extract date."""
    return sample_reading(hotel_id=hotel, arrival_date=date_to_epoch_days(day), prices=prices)


def build_service(
    readings: list[Reading],
    cache: InMemoryCache | None = None,
    ttl: int = 3600,
) -> tuple[PricingService, RecordingStore]:
    """Build a PricingService over a recording store seeded with the given readings."""
    store = RecordingStore(seeded_store(readings))
    service = PricingService(
        store=store,
        cache=cache if cache is not None else InMemoryCache(),
        current_ttl_seconds=ttl,
    )
    return service, store


def differences(
    service: PricingService,
    year: int = 2024,
    month: int = 3,
    years_ago: int = 4,
    cancellable: bool = True,
) -> list[PriceDifference]:
    """Run the service for one month with the test defaults."""
    return service.pre_corona_differences(
        hotels=[HOTEL],
        year=year,
        month=month,
        currency=CURRENCY,
        years_ago=years_ago,
        cancellable=cancellable,
    )


def test_returns_lowest_price_and_difference_against_the_historic_date() -> None:
    """The row carries the lowest current price and current minus historic."""
    service, _ = build_service(
        [
            reading_for(date(2024, 3, 15), [option(506.0), option(612.0)]),
            reading_for(date(2020, 3, 15), [option(400.0), option(450.0)]),
        ]
    )

    rows = differences(service)

    assert rows == [
        PriceDifference(
            hotel=HOTEL,
            arrival_date=date(2024, 3, 15),
            price=506.0,
            currency=CURRENCY,
            difference=106.0,
        )
    ]


def test_ignores_options_in_another_currency() -> None:
    """A cheaper option in a different currency cannot win the lowest price."""
    service, _ = build_service(
        [reading_for(date(2024, 3, 15), [option(10.0, currency="EUR"), option(506.0)])]
    )

    rows = differences(service)

    assert [row.price for row in rows] == [506.0]


def test_ignores_non_cancellable_options_when_cancellable_is_requested() -> None:
    """A cheaper non-cancellable option is excluded when cancellable prices are asked for."""
    service, _ = build_service(
        [reading_for(date(2024, 3, 15), [option(489.0, cancellable=False), option(506.0)])]
    )

    assert [row.price for row in differences(service, cancellable=True)] == [506.0]


def test_keeps_non_cancellable_options_when_cancellable_is_false() -> None:
    """With cancellable False no cancellability filter is applied."""
    service, _ = build_service(
        [reading_for(date(2024, 3, 15), [option(489.0, cancellable=False), option(506.0)])]
    )

    assert [row.price for row in differences(service, cancellable=False)] == [489.0]


def test_maps_the_historic_date_by_years_ago() -> None:
    """The historic lookup targets the same month/day, years_ago years earlier."""
    service, store = build_service([reading_for(date(2024, 3, 15), [option(506.0)])])

    differences(service, years_ago=4)

    assert (HOTEL, date_to_epoch_days(date(2020, 3, 15))) in store.requested_pairs
    assert (HOTEL, date_to_epoch_days(date(2021, 3, 15))) not in store.requested_pairs


def test_missing_historic_yields_a_null_difference_with_the_price_kept() -> None:
    """A historic data gap degrades to difference None, not a dropped row."""
    service, _ = build_service([reading_for(date(2024, 3, 15), [option(506.0)])])

    rows = differences(service)

    assert len(rows) == 1
    assert rows[0].price == 506.0
    assert rows[0].difference is None


def test_historic_reading_without_a_matching_price_yields_a_null_difference() -> None:
    """A historic reading whose options all fail the filters degrades to difference None."""
    service, _ = build_service(
        [
            reading_for(date(2024, 3, 15), [option(506.0)]),
            reading_for(date(2020, 3, 15), [option(400.0, currency="EUR")]),
        ]
    )

    rows = differences(service)

    assert [(row.price, row.difference) for row in rows] == [(506.0, None)]


def test_missing_current_omits_the_row() -> None:
    """Dates with no current reading produce no row at all."""
    service, _ = build_service(
        [
            reading_for(date(2024, 3, 15), [option(506.0)]),
            reading_for(date(2020, 3, 20), [option(400.0)]),
        ]
    )

    rows = differences(service)

    assert [row.arrival_date for row in rows] == [date(2024, 3, 15)]


def test_current_reading_without_a_matching_price_omits_the_row() -> None:
    """A current reading whose options all fail the filters is treated as missing."""
    service, _ = build_service([reading_for(date(2024, 3, 15), [option(506.0, currency="EUR")])])

    assert differences(service) == []


def test_leap_day_yields_a_null_difference_and_no_historic_lookup() -> None:
    """29 February keeps its current price, with no store read for the nonexistent historic date."""
    service, store = build_service([reading_for(date(2024, 2, 29), [option(506.0)])])

    rows = differences(service, year=2024, month=2, years_ago=1)

    expected = {
        (HOTEL, date_to_epoch_days(day))
        for day in [date(2024, 2, d) for d in range(1, 30)]
        + [date(2023, 2, d) for d in range(1, 29)]
    }
    assert [(row.arrival_date, row.difference) for row in rows] == [(date(2024, 2, 29), None)]
    assert store.requested_pairs == expected


def test_reads_the_store_once_for_the_whole_month() -> None:
    """One request makes a single batched store call, not one per hotel/date."""
    service, store = build_service([reading_for(date(2024, 3, 15), [option(506.0)])])

    differences(service)

    assert len(store.calls) == 1


def test_batches_every_current_and_historic_pair_for_every_hotel() -> None:
    """The single store call asks for each hotel's current and historic pair for the month."""
    store = RecordingStore(seeded_store([reading_for(date(2024, 3, 15), [option(506.0)])]))
    service = PricingService(store=store, cache=InMemoryCache(), current_ttl_seconds=3600)

    service.pre_corona_differences(
        hotels=[1, 2],
        year=2024,
        month=3,
        currency=CURRENCY,
        years_ago=4,
        cancellable=True,
    )

    expected = {
        (hotel, date_to_epoch_days(date(year, 3, day)))
        for hotel in (1, 2)
        for year in (2024, 2020)
        for day in range(1, 32)
    }
    assert store.requested_pairs == expected
    assert len(store.calls[0]) == len(expected)


def test_a_cache_hit_avoids_reading_the_store() -> None:
    """Pairs priced by an earlier request are served from the cache, not read again."""
    cache = InMemoryCache()
    readings = [
        reading_for(date(2024, 3, 15), [option(506.0)]),
        reading_for(date(2020, 3, 15), [option(400.0)]),
    ]
    service, store = build_service(readings, cache=cache)
    first = differences(service)
    assert (HOTEL, date_to_epoch_days(date(2024, 3, 15))) in store.requested_pairs

    second_service, second_store = build_service(readings, cache=cache)
    second = differences(second_service)

    assert second == first
    assert (HOTEL, date_to_epoch_days(date(2024, 3, 15))) not in second_store.requested_pairs
    assert (HOTEL, date_to_epoch_days(date(2020, 3, 15))) not in second_store.requested_pairs


def test_a_cache_miss_populates_the_cache() -> None:
    """A price computed on a miss is written back and reused, even if the store loses it."""
    cache = InMemoryCache()
    service, store = build_service([reading_for(date(2024, 3, 15), [option(506.0)])], cache=cache)
    differences(service)
    assert store.calls != []

    empty_service, _ = build_service([], cache=cache)
    rows = differences(empty_service)

    assert [row.price for row in rows] == [506.0]


def test_expired_current_price_is_read_from_the_store_again() -> None:
    """Once the current-price TTL lapses, the next request goes back to the store."""
    clock = FakeClock()
    cache = InMemoryCache(time_fn=clock)
    readings = [reading_for(date(2024, 3, 15), [option(506.0)])]
    service, _ = build_service(readings, cache=cache, ttl=60)
    differences(service)

    clock.advance(61)
    fresh_service, fresh_store = build_service(readings, cache=cache, ttl=60)
    rows = differences(fresh_service)

    assert [row.price for row in rows] == [506.0]
    assert (HOTEL, date_to_epoch_days(date(2024, 3, 15))) in fresh_store.requested_pairs


def test_historic_prices_are_cached_without_a_ttl() -> None:
    """Historic prices are immutable, so they survive well past the current-price TTL."""
    clock = FakeClock()
    cache = InMemoryCache(time_fn=clock)
    readings = [
        reading_for(date(2024, 3, 15), [option(506.0)]),
        reading_for(date(2020, 3, 15), [option(400.0)]),
    ]
    service, _ = build_service(readings, cache=cache, ttl=60)
    differences(service)

    clock.advance(10_000_000)
    fresh_service, fresh_store = build_service(readings, cache=cache, ttl=60)
    differences(fresh_service)

    assert (HOTEL, date_to_epoch_days(date(2020, 3, 15))) not in fresh_store.requested_pairs


def test_store_unavailable_propagates() -> None:
    """A backend outage is a hard failure and must not be degraded into partial results."""
    service = PricingService(
        store=UnavailableStore(), cache=InMemoryCache(), current_ttl_seconds=3600
    )

    with pytest.raises(StoreUnavailableError):
        differences(service)
