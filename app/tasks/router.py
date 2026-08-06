"""HTTP layer only -- ownership and business rules live in TaskService."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.auth.deps import get_current_user
from app.auth.models import User
from app.common.pagination import Page, PageParams
from app.tasks.deps import get_task_service
from app.tasks.models import Task, TaskPriority, TaskStatus
from app.tasks.repository import TaskFilters
from app.tasks.schemas import TaskCreate, TaskRead, TaskUpdate
from app.tasks.service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    current_user: User = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
) -> Task:
    fields = payload.model_dump(exclude={"project_id"})
    return await service.create(current_user.id, payload.project_id, **fields)


@router.get("", response_model=Page[TaskRead])
async def list_tasks(
    page_params: PageParams = Depends(),
    project_id: UUID | None = Query(default=None),
    status_: TaskStatus | None = Query(default=None, alias="status"),
    priority: TaskPriority | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1, max_length=255),
    current_user: User = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
) -> Page[TaskRead]:
    filters = TaskFilters(project_id=project_id, status=status_, priority=priority, search=search)
    items, total = await service.list(current_user.id, filters, page_params)
    return Page[TaskRead](
        items=[TaskRead.model_validate(item) for item in items],
        total=total,
        page=page_params.page,
        page_size=page_params.page_size,
    )


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
) -> Task:
    return await service.get(task_id, current_user.id)


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    current_user: User = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
) -> Task:
    updates = payload.model_dump(exclude_unset=True)
    return await service.update(task_id, current_user.id, **updates)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
) -> None:
    await service.delete(task_id, current_user.id)
