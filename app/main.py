"""App factory: router registration, middleware, and exception handling.

This is the only place that wires domain exceptions (Section 5.3) to HTTP
responses -- every module raises `AppError` subclasses and never touches
`HTTPException` or a status code directly.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

# Every ORM model must be imported somewhere before the first query runs, so
# that string-based relationship() references (e.g. User.projects ->
# "Project") can resolve against SQLAlchemy's declarative class registry.
from app.auth import models as _auth_models  # noqa: F401
from app.common.exceptions import (
    AccountLockedError,
    ConflictError,
    EmailNotVerifiedError,
    ForbiddenError,
    InvalidCredentialsError,
    InvalidTokenError,
    NotFoundError,
)
from app.core.config import API_V1_PREFIX, PROJECT_NAME
from app.core.db import engine
from app.core.health import router as health_router
from app.core.logging import configure_logging, get_logger, request_id_ctx
from app.core.middleware import RequestIdMiddleware
from app.core.redis import close_redis
from app.projects import models as _projects_models  # noqa: F401
from app.tasks import models as _tasks_models  # noqa: F401

logger = get_logger(__name__)

_EXCEPTION_STATUS_MAP: list[tuple[type[Exception], int]] = [
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (ConflictError, status.HTTP_409_CONFLICT),
    (InvalidCredentialsError, status.HTTP_401_UNAUTHORIZED),
    (InvalidTokenError, status.HTTP_400_BAD_REQUEST),
    (EmailNotVerifiedError, status.HTTP_403_FORBIDDEN),
    (ForbiddenError, status.HTTP_403_FORBIDDEN),
    (AccountLockedError, status.HTTP_423_LOCKED),
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    logger.info("app_startup")
    yield
    await close_redis()
    await engine.dispose()
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=PROJECT_NAME,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api-docs",
    )

    app.add_middleware(RequestIdMiddleware)

    for exc_class, http_status in _EXCEPTION_STATUS_MAP:
        app.add_exception_handler(exc_class, _make_handler(http_status))

    app.include_router(health_router)

    from app.auth.router import router as auth_router
    from app.projects.router import router as projects_router
    from app.tasks.router import router as tasks_router

    app.include_router(auth_router, prefix=API_V1_PREFIX)
    app.include_router(projects_router, prefix=API_V1_PREFIX)
    app.include_router(tasks_router, prefix=API_V1_PREFIX)

    return app


def _make_handler(
    http_status: int,
) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        message = getattr(exc, "message", str(exc))
        extra_headers = {}
        if isinstance(exc, AccountLockedError):
            extra_headers["Retry-After"] = str(exc.retry_after_seconds)

        logger.warning(
            "handled_exception",
            extra={"exception_type": type(exc).__name__, "status_code": http_status},
        )
        return JSONResponse(
            status_code=http_status,
            content={
                "error": type(exc).__name__,
                "message": message,
                "request_id": request_id_ctx.get(),
            },
            headers=extra_headers or None,
        )

    return handler


app = create_app()
