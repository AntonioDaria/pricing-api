"""Integration tests for GET /pricing/pre_corona_difference/."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.adapters.in_memory_cache import InMemoryCache
from app.adapters.in_memory_store import InMemoryPricingStore
from app.middleware import RESPONSE_TIME_HEADER
from app.services.pricing_service import PricingService
from tests.api.conftest import CURRENCY, HOTEL, ClientFactory, UnavailableStore, reading_for

ENDPOINT = "/pricing/pre_corona_difference/"


def query(**overrides: object) -> dict[str, object]:
    """Build a valid query string, with any parameter overridden."""
    params: dict[str, object] = {
        "month": "2026-03",
        "currency": CURRENCY,
        "hotels": [HOTEL],
        "years_ago": 5,
    }
    params.update(overrides)
    return params


def test_happy_path_returns_the_documented_response_shape(seeded_client: TestClient) -> None:
    """A valid request returns 200 and one row with all five documented fields."""
    response = seeded_client.get(ENDPOINT, params=query())

    assert response.status_code == 200
    assert response.json() == {
        "prices": [
            {
                "hotel": HOTEL,
                "price": 506.0,
                "currency": CURRENCY,
                "difference": 106.0,
                "arrival_date": "2026-03-15",
            }
        ]
    }


def test_cancellable_defaults_to_true(seeded_client: TestClient) -> None:
    """Omitting `cancellable` is accepted and returns the cancellable price."""
    response = seeded_client.get(ENDPOINT, params=query())

    assert response.status_code == 200
    assert response.json()["prices"][0]["price"] == 506.0


@pytest.mark.parametrize(
    ("label", "overrides"),
    [
        ("too many hotels", {"hotels": list(range(11))}),
        ("bad month format", {"month": "2026-3"}),
        ("month 13", {"month": "2026-13"}),
        ("month 00", {"month": "2026-00"}),
        ("years_ago 0", {"years_ago": 0}),
        ("years_ago 6", {"years_ago": 6}),
        ("bad currency", {"currency": "sgd"}),
        ("currency too long", {"currency": "SGDX"}),
    ],
)
def test_invalid_parameters_are_rejected(
    seeded_client: TestClient, label: str, overrides: dict[str, object]
) -> None:
    """Every documented validation violation returns 422 rather than reaching the service."""
    response = seeded_client.get(ENDPOINT, params=query(**overrides))

    assert response.status_code == 422, label
    assert "detail" in response.json()


def test_ten_hotels_are_accepted(client_for: ClientFactory) -> None:
    """The hotel limit is inclusive: exactly ten hotels is a valid request."""
    service = PricingService(
        store=InMemoryPricingStore([]), cache=InMemoryCache(), current_ttl_seconds=3600
    )

    response = client_for(service).get(ENDPOINT, params=query(hotels=list(range(10))))

    assert response.status_code == 200


def test_rows_without_a_current_price_are_omitted(seeded_client: TestClient) -> None:
    """Arrival dates with no current reading do not appear in the response at all."""
    response = seeded_client.get(ENDPOINT, params=query())

    assert [row["arrival_date"] for row in response.json()["prices"]] == ["2026-03-15"]


def test_missing_historic_price_returns_a_null_difference(client_for: ClientFactory) -> None:
    """A historic data gap keeps the row, with difference null."""
    service = PricingService(
        store=InMemoryPricingStore([reading_for(date(2026, 3, 15), 506.0)]),
        cache=InMemoryCache(),
        current_ttl_seconds=3600,
    )

    response = client_for(service).get(ENDPOINT, params=query())

    assert response.status_code == 200
    assert response.json()["prices"] == [
        {
            "hotel": HOTEL,
            "price": 506.0,
            "currency": CURRENCY,
            "difference": None,
            "arrival_date": "2026-03-15",
        }
    ]


def test_store_outage_returns_502(client_for: ClientFactory) -> None:
    """A store outage is a hard failure mapped to 502, not a degraded 200."""
    service = PricingService(
        store=UnavailableStore(), cache=InMemoryCache(), current_ttl_seconds=3600
    )

    response = client_for(service).get(ENDPOINT, params=query())

    assert response.status_code == 502
    assert response.json() == {"detail": "Pricing store unavailable."}


def test_response_carries_the_timing_header(seeded_client: TestClient) -> None:
    """Every response reports how long it took to serve, in milliseconds."""
    response = seeded_client.get(ENDPOINT, params=query())

    assert RESPONSE_TIME_HEADER in response.headers
    assert float(response.headers[RESPONSE_TIME_HEADER]) >= 0.0


def test_health_response_is_timed_too(seeded_client: TestClient) -> None:
    """The timing middleware covers every route, not just the pricing endpoint."""
    assert RESPONSE_TIME_HEADER in seeded_client.get("/health").headers
