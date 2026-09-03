"""A small demo dataset seeding the in-memory store so the running endpoint returns rows.

Stand-in for the real key-value store; a Bigtable adapter replaces it.
"""

from datetime import date

from app.domain.dates import date_to_epoch_days, dates_in_month
from app.domain.models import RateOption, Reading

DEMO_HOTELS = (3173269, 3173270)
DEMO_CURRENCY = "SGD"
DEMO_YEAR = 2026
DEMO_MONTH = 10
DEMO_YEARS_AGO = 5

# Arrival days deliberately left without data, to exercise the degradation rules in /docs.
_MISSING_CURRENT_DAYS = (7,)
_MISSING_HISTORIC_DAYS = (14, 15)


def demo_readings() -> list[Reading]:
    """Build the demo readings: a current month and its historic counterpart, with gaps."""
    readings: list[Reading] = []
    for hotel in DEMO_HOTELS:
        readings.extend(_readings_for_month(hotel, DEMO_YEAR, base_price=250.0))
        readings.extend(_readings_for_month(hotel, DEMO_YEAR - DEMO_YEARS_AGO, base_price=180.0))
    return readings


def _readings_for_month(hotel: int, year: int, base_price: float) -> list[Reading]:
    """Build one reading per arrival date of the demo month, skipping the seeded gaps."""
    is_historic = year != DEMO_YEAR
    skipped = _MISSING_HISTORIC_DAYS if is_historic else _MISSING_CURRENT_DAYS
    extract_date = date_to_epoch_days(date(year, DEMO_MONTH, 1))

    return [
        Reading(
            hotel_id=hotel,
            extract_date=extract_date,
            arrival_date=date_to_epoch_days(arrival),
            prices=_prices(base_price + arrival.day * 2 + hotel % 10),
        )
        for arrival in dates_in_month(year, DEMO_MONTH)
        if arrival.day not in skipped
    ]


def _prices(cancellable_price: float) -> list[RateOption]:
    """Build a cancellable and a cheaper non-cancellable option for one reading."""
    return [
        RateOption(
            price_value=cancellable_price,
            currency=DEMO_CURRENCY,
            is_cancellable=True,
            room_name="Deluxe King Room",
        ),
        RateOption(
            price_value=cancellable_price - 20.0,
            currency=DEMO_CURRENCY,
            is_cancellable=False,
            room_name="Deluxe King Room, Non-Refundable",
        ),
    ]
