from typing import Protocol
from uuid import UUID

from sqlalchemy import func, select

from app.common.base_repository import SoftDeleteRepository
from app.common.pagination import PageParams
from app.projects.models import Project


class ProjectRepositoryProtocol(Protocol):
    async def get_by_id(self, entity_id: UUID) -> Project | None: ...
    async def get_by_id_for_owner(self, project_id: UUID, owner_id: UUID) -> Project | None: ...
    async def list_for_owner(
        self, owner_id: UUID, page_params: PageParams
    ) -> tuple[list[Project], int]: ...
    async def add(self, instance: Project) -> Project: ...
    async def delete(self, instance: Project) -> None: ...


class ProjectRepository(SoftDeleteRepository[Project]):
    model = Project

    async def get_by_id_for_owner(self, project_id: UUID, owner_id: UUID) -> Project | None:
        stmt = self._active().where(Project.id == project_id, Project.owner_id == owner_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_owner(
        self, owner_id: UUID, page_params: PageParams
    ) -> tuple[list[Project], int]:
        base_stmt = self._active().where(Project.owner_id == owner_id)

        total = await self.session.scalar(select(func.count()).select_from(base_stmt.subquery()))
        stmt = (
            base_stmt.order_by(Project.created_at.desc())
            .offset(page_params.offset)
            .limit(page_params.limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total or 0
