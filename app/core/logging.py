"""Structured JSON logging (Section 8).

One logging configuration, imported everywhere, so log format is consistent
app-wide -- this is the DRY point for logging. `request_id` is carried via a
ContextVar so middleware can set it once per request and every log line
emitted while handling that request picks it up automatically, with no need
to thread it through every function call.
"""

import logging
import sys
from contextvars import ContextVar
from typing import Any

from pythonjsonlogger.json import JsonFormatter

from app.core.config import get_settings

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

# Fields that must never reach a log line, regardless of what a caller passes
# in `extra`. Enforced here, once, rather than trusted to every call site.
_REDACTED_KEYS = {
    "password",
    "password_hash",
    "hashed_password",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
}


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class RedactingJsonFormatter(JsonFormatter):
    def process_log_record(self, log_record: dict[str, Any]) -> dict[str, Any]:
        for key in list(log_record.keys()):
            if key.lower() in _REDACTED_KEYS:
                log_record[key] = "[REDACTED]"
        result: dict[str, Any] = super().process_log_record(log_record)
        return result


def configure_logging() -> None:
    settings = get_settings()

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        RedactingJsonFormatter("%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s")
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.LOG_LEVEL)

    # Quiet down noisy third-party loggers at the default level.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
