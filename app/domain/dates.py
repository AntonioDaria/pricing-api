"""Pure date helpers: epoch-day conversion and historic arrival mapping."""

from datetime import date, timedelta

_EPOCH = date(1970, 1, 1)


def epoch_days_to_date(days: int) -> date:
    """Convert days-since-epoch to a date, where day 0 is 1970-01-01."""
    return _EPOCH + timedelta(days=days)


def date_to_epoch_days(d: date) -> int:
    """Convert a date to days-since-epoch, where 1970-01-01 is day 0."""
    return (d - _EPOCH).days


def historic_arrival(arrival: date, years_ago: int) -> date | None:
    """Return the same month/day `years_ago` years earlier, or None if that date does not exist.

    Makes a new date with only the year swapped — so 2026-03-15 with years_ago=5 becomes 2021-03-15.
    """
    # If the target year is not a leap year,
    # 29 February maps to None rather than clamping to 28 February.
    try:
        return arrival.replace(year=arrival.year - years_ago)
    except ValueError:
        return None
