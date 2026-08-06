"""User persistence (Section 5.2 -- repositories are the only layer that
knows about SQLAlchemy)."""

from typing import Protocol
from uuid import UUID

from app.auth.models import User
from app.common.base_repository import SoftDeleteRepository


class UserRepositoryProtocol(Protocol):
    """What AuthService actually needs from a user store. AuthService is
    typed against this, not `UserRepository`, so a fake/in-memory
    implementation can stand in for unit tests without touching a database
    (Section 5.2, LSP/DIP)."""

    async def get_by_id(self, entity_id: UUID) -> User | None: ...
    async def get_by_email(self, email: str) -> User | None: ...
    async def add(self, instance: User) -> User: ...
    async def delete(self, instance: User) -> None: ...


class UserRepository(SoftDeleteRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        stmt = self._active().where(User.email == email.lower())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
