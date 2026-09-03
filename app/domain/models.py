"""Domain models: the framework-free types the pricing logic is built on."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ReadingKey:
    """A key into the pricing store, with dates as days-since-epoch."""

    hotel_id: int
    extract_date: int
    arrival_date: int


@dataclass(frozen=True)
class RateOption:
    """A single rate option within a reading, priced in one currency."""

    price_value: float
    currency: str
    is_cancellable: bool
    room_name: str | None = None


@dataclass(frozen=True)
class Reading:
    """One scrape of a hotel's rate options for an arrival date."""

    hotel_id: int
    extract_date: int
    arrival_date: int
    prices: list[RateOption]


@dataclass(frozen=True)
class PriceDifference:
    """A hotel's lowest price for an arrival date, and its difference vs the historic one."""

    hotel: int
    arrival_date: date
    price: float
    currency: str
    difference: float | None
