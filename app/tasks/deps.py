from fastapi import Depends

from app.common.deps import get_project_repository, get_task_repository
from app.projects.repository import ProjectRepository
from app.tasks.repository import TaskRepository
from app.tasks.service import TaskService


def get_task_service(
    task_repository: TaskRepository = Depends(get_task_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
) -> TaskService:
    return TaskService(task_repository, project_repository)
