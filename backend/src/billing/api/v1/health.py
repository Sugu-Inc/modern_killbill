"""Health check endpoints for Kubernetes liveness and readiness probes."""
from datetime import datetime

import structlog
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from redis import asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from billing.config import settings

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK, tags=["Health"])
async def health_check() -> dict[str, str]:
    """
    Liveness probe for Kubernetes.

    Returns basic health status if the service is alive (process running).
    Does not check external dependencies.

    Returns:
        dict: Health status with timestamp
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "0.1.0",
    }


@router.get("/health/ready", tags=["Health"])
async def readiness_check() -> JSONResponse:
    """
    Readiness probe for Kubernetes.

    Verifies service can handle requests by checking:
    - Database connectivity
    - Redis connectivity
    - Stripe API reachability (optional check)

    Returns 200 only if all critical dependencies are healthy.

    Returns:
        JSONResponse: Readiness status with dependency checks
    """
    checks = {
        "database": "unknown",
        "redis": "unknown",
        "stripe": "unknown",
    }
    ready = True

    # Check database connectivity
    try:
        engine = create_async_engine(str(settings.database_url), pool_pre_ping=True)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "connected"
        await engine.dispose()
    except Exception as exc:
        logger.error("database_health_check_failed", error=str(exc))
        checks["database"] = "disconnected"
        ready = False

    # Check Redis connectivity
    try:
        redis_client = aioredis.from_url(str(settings.redis_url), encoding="utf-8", decode_responses=True)
        await redis_client.ping()
        checks["redis"] = "connected"
        await redis_client.close()
    except Exception as exc:
        logger.error("redis_health_check_failed", error=str(exc))
        checks["redis"] = "disconnected"
        ready = False

    # Check Stripe API reachability (non-blocking check)
    try:
        import stripe

        stripe.api_key = settings.stripe_secret_key
        # Simple API call to verify connectivity
        stripe.Account.retrieve()
        checks["stripe"] = "reachable"
    except Exception as exc:
        logger.warning("stripe_health_check_failed", error=str(exc))
        # Stripe is not critical for readiness, just warning
        checks["stripe"] = "unreachable"

    status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "ready": ready,
            "checks": checks,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )
