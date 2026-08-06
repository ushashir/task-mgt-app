"""Real Postgres. Covers the explicit Section 16 scenarios: pagination and
filtering return correct counts at page boundaries, and a soft-deleted task
never appears in list results."""

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.common.pagination import PageParams
from app.core.security import hash_password
from app.projects.models import Project
from app.tasks.models import Task, TaskPriority, TaskStatus
from app.tasks.repository import TaskFilters, TaskRepository

pytestmark = pytest.mark.integration


def make_task(project_id: UUID, title: str, **kwargs: object) -> Task:
    return Task(project_id=project_id, title=title, **kwargs)  # type: ignore[arg-type]


async def _make_owner_and_project(session: AsyncSession) -> tuple[User, Project]:
    user = User(
        email="owner@example.com", password_hash=hash_password("Str0ng!Pass1"), full_name="Owner"
    )
    session.add(user)
    await session.flush()

    project = Project(owner_id=user.id, name="Test Project")
    session.add(project)
    await session.flush()
    return user, project


async def test_pagination_returns_correct_items_and_total_at_page_boundaries(
    db_session: AsyncSession,
):
    owner, project = await _make_owner_and_project(db_session)
    repo = TaskRepository(db_session)
    for i in range(5):
        await repo.add(make_task(project.id, f"Task {i}"))

    page1, total1 = await repo.list_for_owner(
        owner.id, TaskFilters(), PageParams(page=1, page_size=2)
    )
    page2, total2 = await repo.list_for_owner(
        owner.id, TaskFilters(), PageParams(page=2, page_size=2)
    )
    page3, total3 = await repo.list_for_owner(
        owner.id, TaskFilters(), PageParams(page=3, page_size=2)
    )

    assert total1 == total2 == total3 == 5
    assert len(page1) == 2
    assert len(page2) == 2
    assert len(page3) == 1  # last page, partial
    all_ids = {t.id for t in page1 + page2 + page3}
    assert len(all_ids) == 5  # no overlap, nothing skipped


async def test_filter_by_status(db_session: AsyncSession):
    owner, project = await _make_owner_and_project(db_session)
    repo = TaskRepository(db_session)
    await repo.add(make_task(project.id, "Todo task", status=TaskStatus.TODO))
    await repo.add(make_task(project.id, "Done task", status=TaskStatus.DONE))

    items, total = await repo.list_for_owner(
        owner.id, TaskFilters(status=TaskStatus.DONE), PageParams()
    )

    assert total == 1
    assert items[0].title == "Done task"


async def test_filter_by_priority(db_session: AsyncSession):
    owner, project = await _make_owner_and_project(db_session)
    repo = TaskRepository(db_session)
    await repo.add(make_task(project.id, "Urgent", priority=TaskPriority.HIGH))
    await repo.add(make_task(project.id, "Someday", priority=TaskPriority.LOW))

    items, total = await repo.list_for_owner(
        owner.id, TaskFilters(priority=TaskPriority.HIGH), PageParams()
    )

    assert total == 1
    assert items[0].title == "Urgent"


async def test_search_matches_title_or_description(db_session: AsyncSession):
    owner, project = await _make_owner_and_project(db_session)
    repo = TaskRepository(db_session)
    await repo.add(make_task(project.id, "Fix login bug", description="auth is broken"))
    await repo.add(make_task(project.id, "Unrelated", description="nothing to do with it"))

    items, total = await repo.list_for_owner(owner.id, TaskFilters(search="login"), PageParams())
    assert total == 1
    assert items[0].title == "Fix login bug"

    items, total = await repo.list_for_owner(owner.id, TaskFilters(search="broken"), PageParams())
    assert total == 1
    assert items[0].title == "Fix login bug"


async def test_soft_deleted_task_never_appears_in_list_results(db_session: AsyncSession):
    owner, project = await _make_owner_and_project(db_session)
    repo = TaskRepository(db_session)
    task = await repo.add(make_task(project.id, "Temporary"))
    await repo.delete(task)

    items, total = await repo.list_for_owner(owner.id, TaskFilters(), PageParams())

    assert total == 0
    assert items == []
    assert await repo.get_by_id_for_owner(task.id, owner.id) is None


async def test_soft_delete_by_project_marks_all_active_tasks_deleted(db_session: AsyncSession):
    owner, project = await _make_owner_and_project(db_session)
    repo = TaskRepository(db_session)
    for i in range(3):
        await repo.add(make_task(project.id, f"Task {i}"))

    await repo.soft_delete_by_project(project.id)

    items, total = await repo.list_for_owner(owner.id, TaskFilters(), PageParams())
    assert total == 0
