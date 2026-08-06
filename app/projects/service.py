"""Ownership is enforced here, not in the router: every read/update/delete
goes through a get-scoped-to-owner lookup, so a project that exists but
belongs to someone else 404s exactly like one that doesn't exist at all --
no leaking which project IDs are in use."""

from typing import Any
from uuid import UUID

from app.common.exceptions import ProjectNotFoundError
from app.common.pagination import PageParams
from app.projects.models import Project
from app.projects.repository import ProjectRepositoryProtocol
from app.tasks.repository import TaskRepositoryProtocol


class ProjectService:
    def __init__(
        self,
        project_repository: ProjectRepositoryProtocol,
        task_repository: TaskRepositoryProtocol,
    ) -> None:
        self._projects = project_repository
        self._tasks = task_repository

    async def create(self, owner_id: UUID, name: str, description: str | None) -> Project:
        project = Project(owner_id=owner_id, name=name, description=description)
        return await self._projects.add(project)

    async def list(self, owner_id: UUID, page_params: PageParams) -> tuple[list[Project], int]:
        return await self._projects.list_for_owner(owner_id, page_params)

    async def get(self, project_id: UUID, owner_id: UUID) -> Project:
        project = await self._projects.get_by_id_for_owner(project_id, owner_id)
        if project is None:
            raise ProjectNotFoundError("Project not found.")
        return project

    async def update(self, project_id: UUID, owner_id: UUID, **fields: Any) -> Project:
        project = await self.get(project_id, owner_id)
        for key, value in fields.items():
            setattr(project, key, value)
        return project

    async def delete(self, project_id: UUID, owner_id: UUID) -> None:
        project = await self.get(project_id, owner_id)
        # Application-level cascade (Section 6.3): soft-delete every active
        # task under this project in the same transaction.
        await self._tasks.soft_delete_by_project(project.id)
        await self._projects.delete(project)
