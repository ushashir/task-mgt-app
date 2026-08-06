import uuid

import pytest

from app.common.exceptions import ProjectNotFoundError, TaskNotFoundError
from app.tasks.models import TaskPriority, TaskStatus
from app.tasks.service import TaskService
from tests.unit.fakes import FakeProjectRepository, FakeTaskRepository, make_project, make_task

pytestmark = pytest.mark.unit


async def test_create_rejects_a_project_that_is_not_owned_by_the_caller():
    owner_id = uuid.uuid4()
    project = make_project(owner_id=uuid.uuid4())  # belongs to someone else
    service = TaskService(FakeTaskRepository(), FakeProjectRepository([project]))

    with pytest.raises(ProjectNotFoundError):
        await service.create(owner_id, project.id, title="New Task")


async def test_create_succeeds_for_an_owned_project():
    owner_id = uuid.uuid4()
    project = make_project(owner_id=owner_id)
    service = TaskService(FakeTaskRepository(), FakeProjectRepository([project]))

    task = await service.create(
        owner_id, project.id, title="New Task", status=TaskStatus.TODO, priority=TaskPriority.HIGH
    )

    assert task.project_id == project.id
    assert task.title == "New Task"
    assert task.priority == TaskPriority.HIGH


async def test_get_raises_not_found_for_unknown_task():
    service = TaskService(FakeTaskRepository(), FakeProjectRepository())

    with pytest.raises(TaskNotFoundError):
        await service.get(uuid.uuid4(), uuid.uuid4())


async def test_update_applies_only_supplied_fields():
    project_id = uuid.uuid4()
    task = make_task(project_id=project_id, title="Old", status=TaskStatus.TODO)
    service = TaskService(FakeTaskRepository([task]), FakeProjectRepository())

    updated = await service.update(task.id, uuid.uuid4(), status=TaskStatus.DONE)

    assert updated.status == TaskStatus.DONE
    assert updated.title == "Old"


async def test_delete_soft_deletes_the_task():
    project_id = uuid.uuid4()
    task = make_task(project_id=project_id, title="Doomed")
    service = TaskService(FakeTaskRepository([task]), FakeProjectRepository())

    await service.delete(task.id, uuid.uuid4())

    assert task.deleted_at is not None
    with pytest.raises(TaskNotFoundError):
        await service.get(task.id, uuid.uuid4())
