"""Registration, login, and password/email-verification flows (Section 7).

Framework-free on purpose: no FastAPI import here (Section 5.2) so this can
be unit tested with a faked `UserRepositoryProtocol` and a fake/real Redis,
with no HTTP layer or real database involved.
"""

import secrets
import uuid
from collections.abc import Awaitable
from typing import cast

import jwt
from redis.asyncio import Redis

from app.auth.models import User
from app.auth.repository import UserRepositoryProtocol
from app.common.exceptions import (
    AccountLockedError,
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.core.config import Settings, get_settings
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def _email_verify_key(token: str) -> str:
    return f"email_verify:{token}"


def _login_lock_key(email: str) -> str:
    return f"login_lock:{email}"


def _login_attempts_key(email: str) -> str:
    return f"login_attempts:{email}"


def _pwd_reset_key(token: str) -> str:
    return f"pwd_reset:{token}"


def _refresh_token_key(jti: str) -> str:
    return f"refresh_token:{jti}"


def _user_tokens_key(user_id: uuid.UUID) -> str:
    return f"user_refresh_tokens:{user_id}"


class AuthService:
    def __init__(
        self,
        user_repository: UserRepositoryProtocol,
        redis: Redis,
        settings: Settings | None = None,
    ) -> None:
        self._users = user_repository
        self._redis = redis
        self._settings = settings or get_settings()

    async def register(self, email: str, password: str, full_name: str) -> tuple[User, str]:
        """Returns (user, verification_token) -- the caller (router) is
        responsible for emailing the token; this layer only issues it."""
        normalized_email = email.lower()
        if await self._users.get_by_email(normalized_email) is not None:
            raise EmailAlreadyRegisteredError("An account with this email already exists.")

        user = User(
            email=normalized_email,
            password_hash=hash_password(password),
            full_name=full_name,
        )
        user = await self._users.add(user)

        token = secrets.token_urlsafe(32)
        await self._redis.set(
            _email_verify_key(token),
            str(user.id),
            ex=self._settings.EMAIL_VERIFICATION_TTL_HOURS * 3600,
        )
        return user, token

    async def verify_email(self, token: str) -> None:
        key = _email_verify_key(token)
        user_id = await self._redis.get(key)
        if user_id is None:
            raise InvalidTokenError("Verification link is invalid or has expired.")

        user = await self._users.get_by_id(uuid.UUID(user_id))
        if user is None:
            raise InvalidTokenError("Verification link is invalid or has expired.")

        user.is_email_verified = True
        await self._redis.delete(key)

    async def login(self, email: str, password: str) -> tuple[str, str]:
        """Returns (access_token, refresh_token)."""
        normalized_email = email.lower()

        lock_ttl = await self._redis.ttl(_login_lock_key(normalized_email))
        if lock_ttl and lock_ttl > 0:
            raise AccountLockedError(
                "Too many failed login attempts. Try again later.",
                retry_after_seconds=lock_ttl,
            )

        user = await self._users.get_by_email(normalized_email)
        credentials_valid = user is not None and verify_password(password, user.password_hash)

        if not credentials_valid or user is None or not user.is_active:
            await self._register_failed_attempt(normalized_email)
            raise InvalidCredentialsError("Invalid email or password.")

        if not user.is_email_verified:
            raise EmailNotVerifiedError("Please verify your email before logging in.")

        await self._redis.delete(
            _login_attempts_key(normalized_email), _login_lock_key(normalized_email)
        )
        return await self._issue_token_pair(user.id)

    async def _register_failed_attempt(self, email: str) -> None:
        attempts_key = _login_attempts_key(email)
        lockout_seconds = self._settings.LOGIN_LOCKOUT_MINUTES * 60

        count = await self._redis.incr(attempts_key)
        await self._redis.expire(attempts_key, lockout_seconds)  # sliding window

        if count >= self._settings.LOGIN_MAX_ATTEMPTS:
            await self._redis.set(_login_lock_key(email), "1", ex=lockout_seconds)
            await self._redis.delete(attempts_key)

    async def request_password_reset(self, email: str) -> tuple[User, str] | None:
        """Returns None if the email isn't registered -- the router must
        still return its generic response either way (Section 7.1: "Response
        is identical whether or not the email exists")."""
        user = await self._users.get_by_email(email.lower())
        if user is None:
            return None

        token = secrets.token_urlsafe(32)
        await self._redis.set(
            _pwd_reset_key(token),
            str(user.id),
            ex=self._settings.PASSWORD_RESET_TTL_MINUTES * 60,
        )
        return user, token

    async def reset_password(self, token: str, new_password: str) -> None:
        key = _pwd_reset_key(token)
        user_id = await self._redis.get(key)
        if user_id is None:
            raise InvalidTokenError("Reset link is invalid or has expired.")

        user = await self._users.get_by_id(uuid.UUID(user_id))
        if user is None:
            raise InvalidTokenError("Reset link is invalid or has expired.")

        user.password_hash = hash_password(new_password)
        await self._redis.delete(key)
        await self._revoke_all_refresh_tokens(user.id)

    async def refresh_access_token(self, refresh_token: str) -> tuple[str, str]:
        payload = self._decode_refresh_token(refresh_token)
        jti, user_id = payload["jti"], payload["sub"]

        stored_user_id = await self._redis.get(_refresh_token_key(jti))
        if stored_user_id is None or stored_user_id != user_id:
            raise InvalidTokenError("Refresh token is invalid or has expired.")

        await self._redis.delete(_refresh_token_key(jti))
        await cast(Awaitable[int], self._redis.srem(_user_tokens_key(uuid.UUID(user_id)), jti))
        return await self._issue_token_pair(uuid.UUID(user_id))

    async def logout(self, refresh_token: str) -> None:
        """Idempotent: an already-invalid/expired token is treated as
        "already logged out" rather than an error."""
        try:
            payload = self._decode_refresh_token(refresh_token)
        except InvalidTokenError:
            return

        jti, user_id = payload["jti"], payload["sub"]
        await self._redis.delete(_refresh_token_key(jti))
        await cast(Awaitable[int], self._redis.srem(_user_tokens_key(uuid.UUID(user_id)), jti))

    def _decode_refresh_token(self, refresh_token: str) -> dict[str, str]:
        try:
            payload = decode_token(refresh_token)
        except jwt.PyJWTError as exc:
            raise InvalidTokenError("Refresh token is invalid or has expired.") from exc

        if payload.get("type") != TokenType.REFRESH.value:
            raise InvalidTokenError("Refresh token is invalid or has expired.")
        return payload

    async def _issue_token_pair(self, user_id: uuid.UUID) -> tuple[str, str]:
        access_token = create_access_token(user_id)
        refresh_token, jti = create_refresh_token(user_id)

        await self._redis.set(
            _refresh_token_key(jti),
            str(user_id),
            ex=self._settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        )
        await cast(Awaitable[int], self._redis.sadd(_user_tokens_key(user_id), jti))
        return access_token, refresh_token

    async def _revoke_all_refresh_tokens(self, user_id: uuid.UUID) -> None:
        tokens_key = _user_tokens_key(user_id)
        jtis = await cast(Awaitable[set[str]], self._redis.smembers(tokens_key))
        if jtis:
            await self._redis.delete(*(_refresh_token_key(jti) for jti in jtis))
        await self._redis.delete(tokens_key)
