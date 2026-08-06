"""Repository factories shared across modules.

ProjectService needs a TaskRepository (soft-delete cascade on project
delete) and TaskService needs a ProjectRepository (ownership checks) --
putting both factories here, rather than in `app/projects/deps.py` and
`app/tasks/deps.py` importing from each other, avoids a circular import
between the two modules' dependency-wiring files.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.projects.repository import ProjectRepository
from app.tasks.repository import TaskRepository


def get_project_repository(session: AsyncSession = Depends(get_db)) -> ProjectRepository:
    return ProjectRepository(session)


def get_task_repository(session: AsyncSession = Depends(get_db)) -> TaskRepository:
    return TaskRepository(session)
