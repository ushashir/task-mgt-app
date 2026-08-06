"""Ownership is transitive through the parent project: a task's owner is
its project's owner, so every lookup here goes through
`ProjectRepositoryProtocol`/`TaskRepositoryProtocol` methods that already
join on that relationship (Section 6.3)."""

from typing import Any
from uuid import UUID

from app.common.exceptions import ProjectNotFoundError, TaskNotFoundError
from app.common.pagination import PageParams
from app.projects.repository import ProjectRepositoryProtocol
from app.tasks.models import Task
from app.tasks.repository import TaskFilters, TaskRepositoryProtocol


class TaskService:
    def __init__(
        self,
        task_repository: TaskRepositoryProtocol,
        project_repository: ProjectRepositoryProtocol,
    ) -> None:
        self._tasks = task_repository
        self._projects = project_repository

    async def create(self, owner_id: UUID, project_id: UUID, **fields: Any) -> Task:
        project = await self._projects.get_by_id_for_owner(project_id, owner_id)
        if project is None:
            raise ProjectNotFoundError("Project not found.")

        task = Task(project_id=project_id, **fields)
        return await self._tasks.add(task)

    async def list(
        self, owner_id: UUID, filters: TaskFilters, page_params: PageParams
    ) -> tuple[list[Task], int]:
        return await self._tasks.list_for_owner(owner_id, filters, page_params)

    async def get(self, task_id: UUID, owner_id: UUID) -> Task:
        task = await self._tasks.get_by_id_for_owner(task_id, owner_id)
        if task is None:
            raise TaskNotFoundError("Task not found.")
        return task

    async def update(self, task_id: UUID, owner_id: UUID, **fields: Any) -> Task:
        task = await self.get(task_id, owner_id)
        for key, value in fields.items():
            setattr(task, key, value)
        return task

    async def delete(self, task_id: UUID, owner_id: UUID) -> None:
        task = await self.get(task_id, owner_id)
        await self._tasks.delete(task)
