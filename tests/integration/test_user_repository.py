"""Real Postgres, one rolled-back transaction per test (Section 16). Covers
the explicit "soft-deleted rows never returned" scenario, plus the partial
unique index behavior from Section 6.2 (a soft-deleted account must not
block re-registration with the same address)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.repository import UserRepository
from app.core.security import hash_password

pytestmark = pytest.mark.integration


def new_user(email: str) -> User:
    return User(email=email, password_hash=hash_password("Str0ng!Pass1"), full_name="Test User")


async def test_get_by_email_returns_the_active_user(db_session: AsyncSession):
    repo = UserRepository(db_session)
    await repo.add(new_user("active@example.com"))

    found = await repo.get_by_email("active@example.com")

    assert found is not None
    assert found.email == "active@example.com"


async def test_soft_deleted_user_is_not_returned_by_get_by_email(db_session: AsyncSession):
    repo = UserRepository(db_session)
    user = await repo.add(new_user("gone@example.com"))
    await repo.delete(user)

    assert await repo.get_by_email("gone@example.com") is None
    assert await repo.get_by_id(user.id) is None


async def test_soft_deleted_user_does_not_block_reregistration_with_same_email(
    db_session: AsyncSession,
):
    repo = UserRepository(db_session)
    original = await repo.add(new_user("recycle@example.com"))
    await repo.delete(original)

    # The partial unique index only covers deleted_at IS NULL rows, so this
    # insert must succeed even though the email already exists on a
    # soft-deleted row.
    new_account = await repo.add(new_user("recycle@example.com"))

    assert new_account.id != original.id
    found = await repo.get_by_email("recycle@example.com")
    assert found is not None
    assert found.id == new_account.id
