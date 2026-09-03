"""The pricing service: expands a month into lookups and computes pre-corona differences."""

from dataclasses import dataclass
from datetime import date

import structlog

from app.domain.dates import date_to_epoch_days, dates_in_month, historic_arrival
from app.domain.models import PriceDifference
from app.domain.pricing import lowest_price
from app.services.ports import Cache, HotelArrival, PricingStore

logger = structlog.get_logger(__name__)


class PricingService:
    """Computes each hotel's lowest price per arrival date and its difference vs X years ago."""

    def __init__(self, store: PricingStore, cache: Cache, current_ttl_seconds: int) -> None:
        """Build the service over a pricing store and a cache, with the current-price TTL."""
        self._store = store
        self._cache = cache
        self._current_ttl_seconds = current_ttl_seconds

    def pre_corona_differences(
        self,
        hotels: list[int],
        year: int,
        month: int,
        currency: str,
        years_ago: int,
        cancellable: bool,
    ) -> list[PriceDifference]:
        """Return one row per hotel per arrival date in the month, omitting rows with no price.

        `difference` is None when the historic price is missing. Propagates
        StoreUnavailableError, which is a hard failure rather than a degraded row.
        """
        plan = self._expand_work_set(hotels, year, month, years_ago)
        current_pairs = {row.current_pair for row in plan}
        historic_pairs = {row.historic_pair for row in plan if row.historic_pair is not None}

        needed = current_pairs | historic_pairs
        prices, misses = self._read_cache(needed, currency, cancellable)
        cache_hits = len(prices)
        prices |= self._read_store(misses, current_pairs, currency, cancellable)

        rows = self._assemble(plan, prices, currency)
        logger.info(
            "priced_month",
            hotels=len(hotels),
            pairs_requested=len(needed),
            cache_hits=cache_hits,
            store_misses=len(misses),
            rows_returned=len(rows),
        )
        return rows

    def _expand_work_set(
        self, hotels: list[int], year: int, month: int, years_ago: int
    ) -> list["_PlannedRow"]:
        """Build the current and historic lookup pairs for every hotel and arrival date."""
        plan: list[_PlannedRow] = []
        for arrival in dates_in_month(year, month):
            historic = historic_arrival(arrival, years_ago)
            for hotel in hotels:
                plan.append(
                    _PlannedRow(
                        hotel=hotel,
                        arrival=arrival,
                        current_pair=(hotel, date_to_epoch_days(arrival)),
                        historic_pair=(
                            None if historic is None else (hotel, date_to_epoch_days(historic))
                        ),
                    )
                )
        return plan

    def _read_cache(
        self, pairs: set[HotelArrival], currency: str, cancellable: bool
    ) -> tuple[dict[HotelArrival, float], list[HotelArrival]]:
        """Split the needed pairs into prices already cached and pairs still to be fetched."""
        cached: dict[HotelArrival, float] = {}
        misses: list[HotelArrival] = []
        for pair in sorted(pairs):
            value = self._cache.get(self._cache_key(pair, currency, cancellable))
            if isinstance(value, float):
                cached[pair] = value
            else:
                misses.append(pair)
        return cached, misses

    def _read_store(
        self,
        misses: list[HotelArrival],
        current_pairs: set[HotelArrival],
        currency: str,
        cancellable: bool,
    ) -> dict[HotelArrival, float]:
        """Batch-read the missing pairs, pick each reading's lowest price and cache the result."""
        if not misses:
            return {}

        fetched: dict[HotelArrival, float] = {}
        for pair, reading in self._store.get_latest_readings(misses).items():
            price = lowest_price(reading.prices, currency=currency, cancellable=cancellable)
            if price is None:
                continue
            fetched[pair] = price
            self._cache.set(
                self._cache_key(pair, currency, cancellable),
                price,
                ttl=self._current_ttl_seconds if pair in current_pairs else None,
            )
        return fetched

    def _assemble(
        self, plan: list["_PlannedRow"], prices: dict[HotelArrival, float], currency: str
    ) -> list[PriceDifference]:
        """Build the result rows, omitting any row without a current price."""
        rows: list[PriceDifference] = []
        for row in plan:
            current = prices.get(row.current_pair)
            if current is None:
                continue
            historic = None if row.historic_pair is None else prices.get(row.historic_pair)
            rows.append(
                PriceDifference(
                    hotel=row.hotel,
                    arrival_date=row.arrival,
                    price=current,
                    currency=currency,
                    difference=None if historic is None else current - historic,
                )
            )
        return rows

    @staticmethod
    def _cache_key(pair: HotelArrival, currency: str, cancellable: bool) -> str:
        """Build the cache key for a pair's lowest price under the requested filters."""
        hotel_id, arrival_date = pair
        return f"lowest:{hotel_id}:{arrival_date}:{currency}:{int(cancellable)}"


@dataclass(frozen=True)
class _PlannedRow:
    """One output row's lookups: the hotel, its arrival date and the pairs to resolve."""

    hotel: int
    arrival: date
    current_pair: HotelArrival
    historic_pair: HotelArrival | None
