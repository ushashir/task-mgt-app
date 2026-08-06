"""FastAPI dependency wiring for the auth module -- the only place that
constructs an `AuthService`/`UserRepository` from a request-scoped session,
and the shared `get_current_user` dependency other modules (projects, tasks)
import to authenticate a request."""

import uuid

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.repository import UserRepository
from app.auth.service import AuthService
from app.common.exceptions import InvalidCredentialsError
from app.core.db import get_db
from app.core.redis import get_redis
from app.core.security import TokenType, decode_token

_bearer_scheme = HTTPBearer()


def get_user_repository(session: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(session)


def get_auth_service(
    user_repository: UserRepository = Depends(get_user_repository),
    redis: Redis = Depends(get_redis),
) -> AuthService:
    return AuthService(user_repository, redis)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    user_repository: UserRepository = Depends(get_user_repository),
) -> User:
    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise InvalidCredentialsError("Invalid or expired token.") from exc

    if payload.get("type") != TokenType.ACCESS.value:
        raise InvalidCredentialsError("Invalid or expired token.")

    user = await user_repository.get_by_id(uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise InvalidCredentialsError("Invalid or expired token.")

    return user
