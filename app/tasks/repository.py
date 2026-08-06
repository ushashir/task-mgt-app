from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy import update as sa_update

from app.common.base_repository import SoftDeleteRepository
from app.common.pagination import PageParams
from app.projects.models import Project
from app.tasks.models import Task, TaskPriority, TaskStatus


@dataclass(frozen=True)
class TaskFilters:
    project_id: UUID | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    search: str | None = None


class TaskRepositoryProtocol(Protocol):
    async def get_by_id(self, entity_id: UUID) -> Task | None: ...
    async def get_by_id_for_owner(self, task_id: UUID, owner_id: UUID) -> Task | None: ...
    async def list_for_owner(
        self, owner_id: UUID, filters: TaskFilters, page_params: PageParams
    ) -> tuple[list[Task], int]: ...
    async def add(self, instance: Task) -> Task: ...
    async def delete(self, instance: Task) -> None: ...
    async def soft_delete_by_project(self, project_id: UUID) -> None: ...


class TaskRepository(SoftDeleteRepository[Task]):
    model = Task

    async def get_by_id_for_owner(self, task_id: UUID, owner_id: UUID) -> Task | None:
        stmt = (
            self._active()
            .join(Project, Project.id == Task.project_id)
            .where(
                Task.id == task_id,
                Project.owner_id == owner_id,
                Project.deleted_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_owner(
        self, owner_id: UUID, filters: TaskFilters, page_params: PageParams
    ) -> tuple[list[Task], int]:
        base_stmt = (
            self._active()
            .join(Project, Project.id == Task.project_id)
            .where(Project.owner_id == owner_id, Project.deleted_at.is_(None))
        )

        if filters.project_id is not None:
            base_stmt = base_stmt.where(Task.project_id == filters.project_id)
        if filters.status is not None:
            base_stmt = base_stmt.where(Task.status == filters.status)
        if filters.priority is not None:
            base_stmt = base_stmt.where(Task.priority == filters.priority)
        if filters.search:
            pattern = f"%{filters.search}%"
            base_stmt = base_stmt.where(
                or_(Task.title.ilike(pattern), Task.description.ilike(pattern))
            )

        total = await self.session.scalar(select(func.count()).select_from(base_stmt.subquery()))
        stmt = (
            base_stmt.order_by(Task.created_at.desc())
            .offset(page_params.offset)
            .limit(page_params.limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total or 0

    async def soft_delete_by_project(self, project_id: UUID) -> None:
        """Application-level cascade (Section 6.3): called by ProjectService
        within the same session/transaction as the project's own soft
        delete, so both commit together."""
        stmt = (
            sa_update(Task)
            .where(Task.project_id == project_id, Task.deleted_at.is_(None))
            .values(deleted_at=func.now())
        )
        await self.session.execute(stmt)
