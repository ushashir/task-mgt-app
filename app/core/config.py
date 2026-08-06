"""Single source of configuration truth (Section 14 of the design doc).

Every environment-dependent value the app needs is declared here, typed and
validated by Pydantic, and loaded from the environment (or a local .env file
in development). Nothing outside this module should read `os.environ`
directly.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Not environment-dependent, so these are plain constants rather than
# Settings fields -- there's nothing for an operator to configure here.
PROJECT_NAME = "Task Management API"
API_V1_PREFIX = "/api/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    ENVIRONMENT: Literal["local", "staging", "production"] = "local"

    DATABASE_URL: str
    REDIS_URL: str

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15

    EMAIL_VERIFICATION_TTL_HOURS: int = 24
    PASSWORD_RESET_TTL_MINUTES: int = 30

    GMAIL_USER: str
    GMAIL_APP_PASSWORD: str
    MAIL_FROM_NAME: str = "Task Manager"

    FRONTEND_URL: str = "http://localhost:3000"

    LOG_LEVEL: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached so the environment is only parsed once per process."""
    return Settings()
