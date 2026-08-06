"""Liveness/readiness endpoint (Section 18) -- wired into the deploy platform's
health check so a broken deploy (DB or Redis unreachable) is caught and rolled
back rather than served to users."""

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.logging import get_logger
from app.core.redis import get_redis

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health")
async def health_check(
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict[str, object]:
    checks = {"database": False, "redis": False}

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        logger.exception("health_check_database_failed")

    try:
        await redis.ping()
        checks["redis"] = True
    except Exception:
        logger.exception("health_check_redis_failed")

    healthy = all(checks.values())
    response.status_code = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if healthy else "unavailable", "checks": checks}
