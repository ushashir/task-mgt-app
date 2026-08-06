"""Soft-delete-aware base repository (Section 13).

Every read method here filters `deleted_at IS NULL` by default, so a
soft-deleted row is invisible to normal queries without each module's
repository having to remember to add that filter itself. `.delete()` is an
UPDATE, never a real DELETE.

Module repositories subclass this and add their own query methods (e.g.
`get_by_email`, `list_for_project`); this class only covers what every
soft-deletable entity needs.
"""

from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mixins import Entity

ModelT = TypeVar("ModelT", bound=Entity)


class SoftDeleteRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _active(self) -> Select[tuple[ModelT]]:
        return select(self.model).where(self.model.deleted_at.is_(None))

    async def get_by_id(self, entity_id: UUID) -> ModelT | None:
        stmt = self._active().where(self.model.id == entity_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: ModelT) -> None:
        instance.mark_deleted()
        await self.session.flush()

    async def count(self, stmt: Select[tuple[ModelT]]) -> int:
        count_stmt = select(func.count()).select_from(stmt.subquery())
        result = await self.session.execute(count_stmt)
        return result.scalar_one()
