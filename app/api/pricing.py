"""The pricing endpoint: validates the query, calls the service and shapes the response."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import RequestValidationError

from app.dependencies import get_pricing_service
from app.schemas.pricing import PriceRow, PricingResponse
from app.services.pricing_service import PricingService

router = APIRouter(prefix="/pricing", tags=["pricing"])

MAX_HOTELS = 10
MONTH_PATTERN = r"^\d{4}-\d{2}$"
CURRENCY_PATTERN = r"^[A-Z]{3}$"


@router.get("/pre_corona_difference/")
def pre_corona_difference(
    month: Annotated[str, Query(pattern=MONTH_PATTERN, description="Arrival month, YYYY-MM.")],
    currency: Annotated[str, Query(pattern=CURRENCY_PATTERN, description="3-letter code.")],
    hotels: Annotated[list[int], Query(min_length=1, max_length=MAX_HOTELS)],
    years_ago: Annotated[int, Query(ge=1, le=5)],
    service: Annotated[PricingService, Depends(get_pricing_service)],
    cancellable: Annotated[bool, Query()] = True,
) -> PricingResponse:
    """Return each hotel's lowest price per arrival date and its difference vs `years_ago` years."""
    year, month_number = _parse_month(month)
    rows = service.pre_corona_differences(
        hotels=hotels,
        year=year,
        month=month_number,
        currency=currency,
        years_ago=years_ago,
        cancellable=cancellable,
    )
    return PricingResponse(
        prices=[
            PriceRow(
                hotel=row.hotel,
                price=row.price,
                currency=row.currency,
                difference=row.difference,
                arrival_date=row.arrival_date,
            )
            for row in rows
        ]
    )


def _parse_month(month: str) -> tuple[int, int]:
    """Split a YYYY-MM string into (year, month), raising a 422 if the month is not 01-12."""
    year_part, month_part = month.split("-")
    month_number = int(month_part)
    if not 1 <= month_number <= 12:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("query", "month"),
                    "msg": "Month must be between 01 and 12.",
                    "input": month,
                }
            ]
        )
    return int(year_part), month_number
