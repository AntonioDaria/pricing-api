"""Health endpoint used for liveness checks and to prove the app boots."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Report that the service is up and able to serve requests."""
    return {"status": "ok"}
