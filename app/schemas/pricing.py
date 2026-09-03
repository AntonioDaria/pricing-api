"""Pydantic schemas for the pre-corona pricing response."""

from datetime import date

from pydantic import BaseModel


class PriceRow(BaseModel):
    """One hotel's lowest price for an arrival date, and its difference vs the historic price."""

    hotel: int
    price: float
    currency: str
    difference: float | None
    arrival_date: date


class PricingResponse(BaseModel):
    """The response body: one row per hotel per arrival date."""

    prices: list[PriceRow]
