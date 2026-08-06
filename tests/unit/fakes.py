"""In-memory test doubles for the unit tier (Section 16: "repositories
mocked/faked", "No" DB/Redis needed). Each fake implements exactly the
Protocol its real counterpart satisfies, so a service under test can't tell
the difference at the type level (Section 5.2, LSP)."""

import uuid
from datetime import UTC, datetime

from app.auth.models import User
from app.projects.models import Project
from app.tasks.models import Task


def make_user(
    *,
    email: str = "user@example.com",
    password_hash: str = "hashed",
    full_name: str = "Test User",
    is_email_verified: bool = False,
    is_active: bool = True,
) -> User:
    user = User(
        email=email,
        password_hash=password_hash,
        full_name=full_name,
        is_email_verified=is_email_verified,
        is_active=is_active,
    )
    user.id = uuid.uuid4()
    user.created_at = datetime.now(UTC)
    user.updated_at = user.created_at
    return user


def make_project(
    *, owner_id: uuid.UUID, name: str = "Project", description: str | None = None
) -> Project:
    project = Project(owner_id=owner_id, name=name, description=description)
    project.id = uuid.uuid4()
    project.created_at = datetime.now(UTC)
    project.updated_at = project.created_at
    return project


def make_task(*, project_id: uuid.UUID, **kwargs: object) -> Task:
    task = Task(project_id=project_id, **kwargs)  # type: ignore[arg-type]
    task.id = uuid.uuid4()
    task.created_at = datetime.now(UTC)
    task.updated_at = task.created_at
    return task


class FakeUserRepository:
    def __init__(self, users: list[User] | None = None) -> None:
        self._users: dict[uuid.UUID, User] = {u.id: u for u in (users or [])}

    async def get_by_id(self, entity_id: uuid.UUID) -> User | None:
        user = self._users.get(entity_id)
        return user if user and user.deleted_at is None else None

    async def get_by_email(self, email: str) -> User | None:
        for user in self._users.values():
            if user.email == email.lower() and user.deleted_at is None:
                return user
        return None

    async def add(self, instance: User) -> User:
        # Simulate the column defaults a real INSERT would apply -- a bare
        # User(...) built by AuthService.register() doesn't get them until
        # SQLAlchemy actually flushes, which this fake never does.
        if instance.id is None:
            instance.id = uuid.uuid4()
        if instance.is_email_verified is None:
            instance.is_email_verified = False
        if instance.is_active is None:
            instance.is_active = True
        self._users[instance.id] = instance
        return instance

    async def delete(self, instance: User) -> None:
        instance.deleted_at = datetime.now(UTC)


class FakeProjectRepository:
    def __init__(self, projects: list[Project] | None = None) -> None:
        self._projects: dict[uuid.UUID, Project] = {p.id: p for p in (projects or [])}

    async def get_by_id(self, entity_id: uuid.UUID) -> Project | None:
        project = self._projects.get(entity_id)
        return project if project and project.deleted_at is None else None

    async def get_by_id_for_owner(
        self, project_id: uuid.UUID, owner_id: uuid.UUID
    ) -> Project | None:
        project = self._projects.get(project_id)
        if project and project.deleted_at is None and project.owner_id == owner_id:
            return project
        return None

    async def list_for_owner(
        self, owner_id: uuid.UUID, page_params: object
    ) -> tuple[list[Project], int]:
        matches = [
            p for p in self._projects.values() if p.owner_id == owner_id and p.deleted_at is None
        ]
        return matches, len(matches)

    async def add(self, instance: Project) -> Project:
        if instance.id is None:
            instance.id = uuid.uuid4()
        self._projects[instance.id] = instance
        return instance

    async def delete(self, instance: Project) -> None:
        instance.deleted_at = datetime.now(UTC)


class FakeTaskRepository:
    def __init__(self, tasks: list[Task] | None = None) -> None:
        self._tasks: dict[uuid.UUID, Task] = {t.id: t for t in (tasks or [])}
        self.soft_delete_by_project_calls: list[uuid.UUID] = []

    async def get_by_id(self, entity_id: uuid.UUID) -> Task | None:
        task = self._tasks.get(entity_id)
        return task if task and task.deleted_at is None else None

    async def get_by_id_for_owner(self, task_id: uuid.UUID, owner_id: uuid.UUID) -> Task | None:
        # Fakes don't need the real join-through-project logic -- the
        # owning service is what's under test, so ownership is decided by
        # whatever the test wired up via add().
        return await self.get_by_id(task_id)

    async def list_for_owner(
        self, owner_id: uuid.UUID, filters: object, page_params: object
    ) -> tuple[list[Task], int]:
        matches = [t for t in self._tasks.values() if t.deleted_at is None]
        return matches, len(matches)

    async def add(self, instance: Task) -> Task:
        if instance.id is None:
            instance.id = uuid.uuid4()
        self._tasks[instance.id] = instance
        return instance

    async def delete(self, instance: Task) -> None:
        instance.deleted_at = datetime.now(UTC)

    async def soft_delete_by_project(self, project_id: uuid.UUID) -> None:
        self.soft_delete_by_project_calls.append(project_id)
        for task in self._tasks.values():
            if task.project_id == project_id and task.deleted_at is None:
                task.deleted_at = datetime.now(UTC)


class FakeRedis:
    """Implements exactly the subset of the redis-py async API AuthService
    uses. No real expiry -- tests assert on the `ex=`/`expire()` value
    passed in, not on time actually elapsing (real TTL expiry is an
    integration-tier concern, tested against real Redis)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.sets: dict[str, set[str]] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def delete(self, *keys: str) -> int:
        count = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                count += 1
            self.ttls.pop(key, None)
        return count

    async def ttl(self, key: str) -> int:
        if key not in self.store:
            return -2
        return self.ttls.get(key, -1)

    async def incr(self, key: str) -> int:
        current = int(self.store.get(key, "0")) + 1
        self.store[key] = str(current)
        return current

    async def expire(self, key: str, seconds: int) -> bool:
        if key in self.store:
            self.ttls[key] = seconds
        return True

    async def sadd(self, key: str, *values: str) -> int:
        bucket = self.sets.setdefault(key, set())
        before = len(bucket)
        bucket.update(values)
        return len(bucket) - before

    async def srem(self, key: str, *values: str) -> int:
        bucket = self.sets.get(key, set())
        removed = sum(1 for v in values if v in bucket)
        bucket.difference_update(values)
        return removed

    async def smembers(self, key: str) -> "set[str]":
        return set(self.sets.get(key, set()))
