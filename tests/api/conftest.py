"""Fixtures building a TestClient whose pricing service is a seeded in-memory stack."""

from collections.abc import Callable, Iterable, Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.adapters.in_memory_cache import InMemoryCache
from app.adapters.in_memory_store import InMemoryPricingStore
from app.dependencies import get_pricing_service
from app.domain.dates import date_to_epoch_days
from app.domain.models import RateOption, Reading
from app.errors import StoreUnavailableError
from app.main import create_app
from app.services.ports import HotelArrival
from app.services.pricing_service import PricingService

HOTEL = 3173269
CURRENCY = "SGD"


class UnavailableStore:
    """A PricingStore standing in for a backend outage."""

    def get_latest_readings(self, pairs: Iterable[HotelArrival]) -> dict[HotelArrival, Reading]:
        """Raise StoreUnavailableError, as a real adapter would on an outage."""
        raise StoreUnavailableError("backend down")


def reading_for(day: date, price: float, hotel: int = HOTEL, currency: str = CURRENCY) -> Reading:
    """Build a one-option cancellable reading for a hotel's arrival date."""
    return Reading(
        hotel_id=hotel,
        extract_date=date_to_epoch_days(date(2026, 1, 1)),
        arrival_date=date_to_epoch_days(day),
        prices=[RateOption(price_value=price, currency=currency, is_cancellable=True)],
    )


ClientFactory = Callable[[PricingService], TestClient]


@pytest.fixture
def client_for() -> Iterator[ClientFactory]:
    """Return a factory building a TestClient whose pricing service is the one given."""
    clients: list[TestClient] = []

    def factory(service: PricingService) -> TestClient:
        application = create_app()
        application.dependency_overrides[get_pricing_service] = lambda: service
        client = TestClient(application)
        clients.append(client)
        return client

    yield factory

    for client in clients:
        client.close()


@pytest.fixture
def seeded_client(client_for: ClientFactory) -> TestClient:
    """A client whose store holds a current and a historic reading for one arrival date."""
    service = PricingService(
        store=InMemoryPricingStore(
            [reading_for(date(2026, 3, 15), 506.0), reading_for(date(2021, 3, 15), 400.0)]
        ),
        cache=InMemoryCache(),
        current_ttl_seconds=3600,
    )
    return client_for(service)
