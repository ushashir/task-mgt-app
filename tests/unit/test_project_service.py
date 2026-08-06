import uuid

import pytest

from app.common.exceptions import ProjectNotFoundError
from app.projects.service import ProjectService
from tests.unit.fakes import FakeProjectRepository, FakeTaskRepository, make_project

pytestmark = pytest.mark.unit


def make_service(projects=None):
    return ProjectService(FakeProjectRepository(projects), FakeTaskRepository())


async def test_create_project_assigns_owner():
    owner_id = uuid.uuid4()
    service = make_service()

    project = await service.create(owner_id, "New Project", "desc")

    assert project.owner_id == owner_id
    assert project.name == "New Project"


async def test_get_raises_not_found_for_someone_elses_project():
    owner_id = uuid.uuid4()
    other_owner_id = uuid.uuid4()
    project = make_project(owner_id=owner_id)
    service = make_service([project])

    with pytest.raises(ProjectNotFoundError):
        await service.get(project.id, other_owner_id)


async def test_get_raises_not_found_for_unknown_id():
    service = make_service()

    with pytest.raises(ProjectNotFoundError):
        await service.get(uuid.uuid4(), uuid.uuid4())


async def test_update_applies_only_supplied_fields():
    owner_id = uuid.uuid4()
    project = make_project(owner_id=owner_id, name="Old Name", description="Old desc")
    service = make_service([project])

    updated = await service.update(project.id, owner_id, name="New Name")

    assert updated.name == "New Name"
    assert updated.description == "Old desc"  # untouched


async def test_update_can_explicitly_clear_a_field_to_none():
    owner_id = uuid.uuid4()
    project = make_project(owner_id=owner_id, description="Old desc")
    service = make_service([project])

    updated = await service.update(project.id, owner_id, description=None)

    assert updated.description is None


async def test_delete_cascades_to_tasks_in_the_same_project():
    owner_id = uuid.uuid4()
    project = make_project(owner_id=owner_id)
    task_repo = FakeTaskRepository()
    service = ProjectService(FakeProjectRepository([project]), task_repo)

    await service.delete(project.id, owner_id)

    assert project.deleted_at is not None
    assert task_repo.soft_delete_by_project_calls == [project.id]


async def test_list_returns_only_the_owners_projects():
    owner_id = uuid.uuid4()
    mine = make_project(owner_id=owner_id, name="Mine")
    someone_elses = make_project(owner_id=uuid.uuid4(), name="Not Mine")
    service = make_service([mine, someone_elses])

    items, total = await service.list(owner_id, page_params=None)

    assert total == 1
    assert items == [mine]
