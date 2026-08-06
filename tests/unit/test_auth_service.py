"""Section 16 explicit scenarios: lockout triggers at the configured
threshold, an expired/unknown verification or reset token is rejected.
Repositories and Redis are faked -- no DB, no network (Section 16 unit tier:
"No" DB/Redis needed)."""

import pytest

from app.auth.service import AuthService
from app.common.exceptions import (
    AccountLockedError,
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.core.security import hash_password, verify_password
from tests.unit.fakes import FakeRedis, FakeUserRepository, make_user

pytestmark = pytest.mark.unit


def make_service(users=None):
    return AuthService(FakeUserRepository(users), FakeRedis())


async def test_register_hashes_password_and_issues_verification_token():
    service = make_service()

    user, token = await service.register("New@Example.com", "Str0ng!Pass1", "New User")

    assert user.email == "new@example.com"  # normalized to lowercase
    assert user.password_hash != "Str0ng!Pass1"
    assert verify_password("Str0ng!Pass1", user.password_hash)
    assert await service._redis.get(f"email_verify:{token}") == str(user.id)


async def test_register_rejects_duplicate_email():
    existing = make_user(email="taken@example.com")
    service = make_service([existing])

    with pytest.raises(EmailAlreadyRegisteredError):
        await service.register("taken@example.com", "Str0ng!Pass1", "Someone Else")


async def test_verify_email_with_unknown_token_is_rejected():
    service = make_service()

    with pytest.raises(InvalidTokenError):
        await service.verify_email("does-not-exist")


async def test_verify_email_marks_user_verified_and_is_single_use():
    service = make_service()
    user, token = await service.register("new@example.com", "Str0ng!Pass1", "New User")
    assert user.is_email_verified is False

    await service.verify_email(token)
    assert user.is_email_verified is True

    with pytest.raises(InvalidTokenError):
        await service.verify_email(token)  # replay


async def test_login_rejects_wrong_password():
    user = make_user(
        email="a@example.com", password_hash=hash_password("Correct1!"), is_email_verified=True
    )
    service = make_service([user])

    with pytest.raises(InvalidCredentialsError):
        await service.login("a@example.com", "Wrong1!")


async def test_login_blocks_unverified_email_after_correct_password():
    user = make_user(
        email="a@example.com", password_hash=hash_password("Correct1!"), is_email_verified=False
    )
    service = make_service([user])

    with pytest.raises(EmailNotVerifiedError):
        await service.login("a@example.com", "Correct1!")


async def test_login_succeeds_and_clears_attempt_counters():
    user = make_user(
        email="a@example.com", password_hash=hash_password("Correct1!"), is_email_verified=True
    )
    service = make_service([user])
    await service._redis.set("login_attempts:a@example.com", "3")

    access_token, refresh_token = await service.login("a@example.com", "Correct1!")

    assert access_token and refresh_token
    assert await service._redis.get("login_attempts:a@example.com") is None


async def test_login_locks_out_after_configured_threshold():
    user = make_user(
        email="a@example.com", password_hash=hash_password("Correct1!"), is_email_verified=True
    )
    service = make_service([user])
    max_attempts = service._settings.LOGIN_MAX_ATTEMPTS

    # Every failed attempt up to and including the threshold-crossing one
    # gets the same generic InvalidCredentialsError -- the app doesn't
    # announce "you just got locked out" on that request, only on the next
    # one (matches the manually-verified API behavior: 5x 401, then 423).
    for _ in range(max_attempts):
        with pytest.raises(InvalidCredentialsError):
            await service.login("a@example.com", "Wrong1!")

    with pytest.raises(AccountLockedError):
        await service.login("a@example.com", "Wrong1!")  # (max_attempts + 1)th call

    lock_ttl = await service._redis.ttl("login_lock:a@example.com")
    assert lock_ttl == service._settings.LOGIN_LOCKOUT_MINUTES * 60
    assert await service._redis.get("login_attempts:a@example.com") is None  # reset on lock

    # Even the CORRECT password is rejected while locked.
    with pytest.raises(AccountLockedError):
        await service.login("a@example.com", "Correct1!")


async def test_forgot_password_returns_none_for_unknown_email():
    service = make_service()

    result = await service.request_password_reset("nobody@example.com")

    assert result is None


async def test_reset_password_with_unknown_token_is_rejected():
    service = make_service()

    with pytest.raises(InvalidTokenError):
        await service.reset_password("bogus-token", "NewStr0ng!Pass1")


async def test_reset_password_changes_hash_and_revokes_refresh_tokens():
    user = make_user(
        email="a@example.com", password_hash=hash_password("Old1!Pass"), is_email_verified=True
    )
    service = make_service([user])
    old_hash = user.password_hash
    _, refresh_token = await service._issue_token_pair(user.id)

    result = await service.request_password_reset("a@example.com")
    assert result is not None
    _, reset_token = result

    await service.reset_password(reset_token, "New1!Pass")

    assert user.password_hash != old_hash
    assert verify_password("New1!Pass", user.password_hash)
    # the refresh token issued before the reset must now be rejected
    with pytest.raises(InvalidTokenError):
        await service.refresh_access_token(refresh_token)


async def test_refresh_rotates_token_and_rejects_reuse_of_the_old_one():
    user = make_user(
        email="a@example.com", password_hash=hash_password("Correct1!"), is_email_verified=True
    )
    service = make_service([user])
    _, refresh_token = await service.login("a@example.com", "Correct1!")

    new_access, new_refresh = await service.refresh_access_token(refresh_token)
    assert new_access and new_refresh
    assert new_refresh != refresh_token

    with pytest.raises(InvalidTokenError):
        await service.refresh_access_token(refresh_token)  # old one is now dead


async def test_logout_invalidates_the_refresh_token():
    user = make_user(
        email="a@example.com", password_hash=hash_password("Correct1!"), is_email_verified=True
    )
    service = make_service([user])
    _, refresh_token = await service.login("a@example.com", "Correct1!")

    await service.logout(refresh_token)

    with pytest.raises(InvalidTokenError):
        await service.refresh_access_token(refresh_token)


async def test_logout_is_idempotent_for_garbage_input():
    service = make_service()

    await service.logout("not-a-real-token")  # must not raise
