"""Request-correlation middleware (Section 8).

Assigns a request ID to every incoming request -- reusing an inbound
`X-Request-ID` header if the caller supplied one, so correlation survives a
hop through a gateway/load balancer -- and echoes it back on the response.
"""

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger, request_id_ctx

logger = get_logger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        token = request_id_ctx.set(request_id)
        start = time.perf_counter()

        try:
            try:
                response = await call_next(request)
            except Exception:
                logger.exception(
                    "request_failed",
                    extra={"method": request.method, "path": request.url.path},
                )
                raise

            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "request_completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            request_id_ctx.reset(token)
