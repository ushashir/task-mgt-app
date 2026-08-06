"""Domain exceptions (Section 5.3).

Services raise these -- never an HTTPException, so service code stays free
of any FastAPI/Starlette import. A single handler set in `app/main.py` maps
each of these to a consistent HTTP response shape.
"""


class AppError(Exception):
    """Base class for every domain-level error the app raises on purpose."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(AppError):
    pass


class UserNotFoundError(NotFoundError):
    pass


class ProjectNotFoundError(NotFoundError):
    pass


class TaskNotFoundError(NotFoundError):
    pass


class ConflictError(AppError):
    pass


class EmailAlreadyRegisteredError(ConflictError):
    pass


class InvalidCredentialsError(AppError):
    pass


class AccountLockedError(AppError):
    def __init__(self, message: str, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


class EmailNotVerifiedError(AppError):
    pass


class InvalidTokenError(AppError):
    """Raised for a missing/expired/malformed verification, reset, or refresh token."""


class ForbiddenError(AppError):
    """Raised when an authenticated user acts on a resource they don't own."""
