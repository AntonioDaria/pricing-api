"""Error mapping: turns typed domain errors into the API's JSON error responses."""

import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.errors import StoreUnavailableError

logger = structlog.get_logger(__name__)


async def store_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    """Map a store outage to 502, using the same `detail` shape as FastAPI's other errors."""
    logger.error("store_unavailable", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": "Pricing store unavailable."},
    )


def register_error_handlers(application: FastAPI) -> None:
    """Register the application's exception handlers in one place."""
    application.add_exception_handler(StoreUnavailableError, store_unavailable_handler)
