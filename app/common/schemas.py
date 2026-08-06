"""Consistent error response shape, used by every exception handler in main.py."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: str
    message: str
    request_id: str | None = None
