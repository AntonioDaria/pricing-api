"""In-memory PricingStore adapter: a seeded fake standing in for the KV store."""

from collections.abc import Iterable
from typing import TYPE_CHECKING

import structlog

from app.domain.models import Reading, ReadingKey
from app.services.ports import HotelArrival

logger = structlog.get_logger(__name__)


class InMemoryPricingStore:
    """A PricingStore backed by readings held in memory, with a latest-extract index."""

    def __init__(self, readings: Iterable[Reading]) -> None:
        """Index the given readings by key and record the newest extract per (hotel, arrival)."""
        self._readings: dict[ReadingKey, Reading] = {}
        self._latest_extract: dict[HotelArrival, int] = {}  # side index for get_latest_readings

        for reading in readings:
            key = ReadingKey(
                hotel_id=reading.hotel_id,
                extract_date=reading.extract_date,
                arrival_date=reading.arrival_date,
            )
            # Store the reading under its key
            self._readings[key] = reading

            pair: HotelArrival = (reading.hotel_id, reading.arrival_date)
            known_latest = self._latest_extract.get(pair)
            if known_latest is None or reading.extract_date > known_latest:
                self._latest_extract[pair] = reading.extract_date

    def get_latest_readings(self, pairs: Iterable[HotelArrival]) -> dict[HotelArrival, Reading]:
        """Return the newest reading per pair, omitting pairs with no data."""
        requested = list(pairs)
        found: dict[HotelArrival, Reading] = {}

        for pair in requested:
            # index lookup for the newest extract_date for this (hotel, arrival)
            extract_date = self._latest_extract.get(pair)
            if extract_date is None:
                continue
            hotel_id, arrival_date = pair
            key = ReadingKey(
                hotel_id=hotel_id, extract_date=extract_date, arrival_date=arrival_date
            )
            found[pair] = self._readings[key]

        logger.info("resolved_latest_readings", requested=len(requested), found=len(found))
        return found


if TYPE_CHECKING:
    from app.services.ports import PricingStore

    _store_conforms: PricingStore = InMemoryPricingStore(readings=[])
