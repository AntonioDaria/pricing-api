"""Tests for the domain date helpers."""

from datetime import date

import pytest

from app.domain.dates import date_to_epoch_days, epoch_days_to_date, historic_arrival


@pytest.mark.parametrize(
    ("days", "expected"),
    [(0, date(1970, 1, 1)), (19038, date(2022, 2, 15)), (19054, date(2022, 3, 3))],
)
def test_epoch_days_to_date_matches_known_values(days: int, expected: date) -> None:
    """Days-since-epoch convert to the expected calendar dates."""
    assert epoch_days_to_date(days) == expected


def test_date_to_epoch_days_is_inverse_of_epoch_days_to_date() -> None:
    """Converting epoch days to a date and back returns the original number."""
    for days in (0, 1, 19038, 19054, 25000):
        assert date_to_epoch_days(epoch_days_to_date(days)) == days


def test_historic_arrival_keeps_month_and_day() -> None:
    """The historic arrival is the same month/day, `years_ago` years earlier."""
    assert historic_arrival(date(2026, 3, 15), 5) == date(2021, 3, 15)


def test_historic_arrival_returns_none_for_nonexistent_date() -> None:
    """29 February maps to None in a non-leap target year rather than clamping to the 28th."""
    assert historic_arrival(date(2024, 2, 29), 1) is None


def test_historic_arrival_allows_leap_day_in_a_leap_year() -> None:
    """29 February maps cleanly onto another leap year."""
    assert historic_arrival(date(2024, 2, 29), 4) == date(2020, 2, 29)
