"""Request/response models, split per use case (Section 5.2, ISP) rather
than one bloated User schema doing double duty as both input and output."""

import re
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

_PASSWORD_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[A-Z]"), "one uppercase letter"),
    (re.compile(r"[a-z]"), "one lowercase letter"),
    (re.compile(r"[0-9]"), "one digit"),
    (re.compile(r"[^A-Za-z0-9]"), "one special character"),
]


def _validate_password_strength(value: str) -> str:
    missing = [description for pattern, description in _PASSWORD_RULES if not pattern.search(value)]
    if missing:
        raise ValueError(f"Password must contain at least {', '.join(missing)}.")
    return value


StrongPassword = Annotated[
    str,
    Field(min_length=8, max_length=128),
    AfterValidator(_validate_password_strength),
]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: StrongPassword
    full_name: str = Field(min_length=1, max_length=255)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    is_email_verified: bool
    is_active: bool
    created_at: datetime


class VerifyEmailRequest(BaseModel):
    token: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: StrongPassword
