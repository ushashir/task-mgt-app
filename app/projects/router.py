"""HTTP layer only -- ownership and business rules live in ProjectService."""

from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.auth.deps import get_current_user
from app.auth.models import User
from app.common.pagination import Page, PageParams
from app.projects.deps import get_project_service
from app.projects.models import Project
from app.projects.schemas import ProjectCreate, ProjectRead, ProjectUpdate
from app.projects.service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
) -> Project:
    return await service.create(current_user.id, payload.name, payload.description)


@router.get("", response_model=Page[ProjectRead])
async def list_projects(
    page_params: PageParams = Depends(),
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
) -> Page[ProjectRead]:
    items, total = await service.list(current_user.id, page_params)
    return Page[ProjectRead](
        items=[ProjectRead.model_validate(item) for item in items],
        total=total,
        page=page_params.page,
        page_size=page_params.page_size,
    )


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
) -> Project:
    return await service.get(project_id, current_user.id)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
) -> Project:
    updates = payload.model_dump(exclude_unset=True)
    return await service.update(project_id, current_user.id, **updates)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
) -> None:
    await service.delete(project_id, current_user.id)
