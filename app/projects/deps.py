from fastapi import Depends

from app.common.deps import get_project_repository, get_task_repository
from app.projects.repository import ProjectRepository
from app.projects.service import ProjectService
from app.tasks.repository import TaskRepository


def get_project_service(
    project_repository: ProjectRepository = Depends(get_project_repository),
    task_repository: TaskRepository = Depends(get_task_repository),
) -> ProjectService:
    return ProjectService(project_repository, task_repository)
