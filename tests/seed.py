"""Seed data builders: the deck's sample reading and a store seeded with it."""

from collections.abc import Iterable

from app.adapters.in_memory_store import InMemoryPricingStore
from app.domain.models import RateOption, Reading

SAMPLE_HOTEL_ID = 3173269
SAMPLE_EXTRACT_DATE = 19038
SAMPLE_ARRIVAL_DATE = 19054
SAMPLE_CURRENCY = "SGD"


def sample_prices() -> list[RateOption]:
    """Return the deck's sample rate options, in SGD, including the 506 option."""
    return [
        RateOption(
            price_value=506.0,
            currency=SAMPLE_CURRENCY,
            is_cancellable=True,
            room_name="Deluxe King Room",
        ),
        RateOption(
            price_value=612.0,
            currency=SAMPLE_CURRENCY,
            is_cancellable=True,
            room_name="Premier King Room",
        ),
        RateOption(
            price_value=489.0,
            currency=SAMPLE_CURRENCY,
            is_cancellable=False,
            room_name="Deluxe King Room, Non-Refundable",
        ),
    ]


def sample_reading(
    hotel_id: int = SAMPLE_HOTEL_ID,
    extract_date: int = SAMPLE_EXTRACT_DATE,
    arrival_date: int = SAMPLE_ARRIVAL_DATE,
    prices: list[RateOption] | None = None,
) -> Reading:
    """Return the deck's sample reading, with any field overridden by the given arguments."""
    return Reading(
        hotel_id=hotel_id,
        extract_date=extract_date,
        arrival_date=arrival_date,
        prices=sample_prices() if prices is None else prices,
    )


def seeded_store(readings: Iterable[Reading] | None = None) -> InMemoryPricingStore:
    """Return an InMemoryPricingStore holding the given readings, or the sample reading."""
    return InMemoryPricingStore(readings if readings is not None else [sample_reading()])
