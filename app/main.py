"""Application entry point: builds the FastAPI app and wires its routers."""

from fastapi import FastAPI

from app.api import health
from app.logging import configure_logging


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    configure_logging()
    application = FastAPI(
        title="Pre-Corona Pricing API",
        description="Current lowest hotel prices and their difference vs X years ago.",
        version="0.1.0",
    )
    application.include_router(health.router)
    return application


app = create_app()
