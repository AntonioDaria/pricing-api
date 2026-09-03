"""HTTP middleware: times every request and records how long it took to serve."""

import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)

RESPONSE_TIME_HEADER = "X-Response-Time-ms"


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Logs one line per request with its duration, and returns the duration as a header."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Time the request, log method/path/status/duration_ms and set the timing header."""
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)

        response.headers[RESPONSE_TIME_HEADER] = str(duration_ms)
        logger.info(
            "request_handled",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response
