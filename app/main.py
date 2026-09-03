"""Application entry point: builds the FastAPI app and wires its routers."""

from fastapi import FastAPI

from app.api import health, pricing
from app.api.errors import register_error_handlers
from app.dependencies import register_pricing_service
from app.logging import configure_logging
from app.middleware import RequestTimingMiddleware


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    configure_logging()
    application = FastAPI(
        title="Pre-Corona Pricing API",
        description="Current lowest hotel prices and their difference vs X years ago.",
        version="0.1.0",
    )
    application.add_middleware(RequestTimingMiddleware)
    register_error_handlers(application)
    register_pricing_service(application)

    application.include_router(health.router)
    application.include_router(pricing.router)
    return application


app = create_app()
