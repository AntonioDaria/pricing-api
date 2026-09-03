"""Dependency wiring: builds the service graph at startup and exposes it to the routes."""

from fastapi import FastAPI, Request

from app.adapters.demo_data import demo_readings
from app.adapters.in_memory_cache import InMemoryCache
from app.adapters.in_memory_store import InMemoryPricingStore
from app.config import get_settings
from app.services.pricing_service import PricingService


def build_pricing_service() -> PricingService:
    """Build the pricing service over the in-memory adapters, using settings read at startup."""
    settings = get_settings()
    return PricingService(
        store=InMemoryPricingStore(demo_readings()),
        cache=InMemoryCache(),
        current_ttl_seconds=settings.current_price_ttl_seconds,
    )


def register_pricing_service(application: FastAPI) -> None:
    """Attach a pricing service to the app, so invalid configuration fails at boot."""
    application.state.pricing_service = build_pricing_service()


def get_pricing_service(request: Request) -> PricingService:
    """Return the application's pricing service; overridable in tests."""
    service: PricingService = request.app.state.pricing_service
    return service
