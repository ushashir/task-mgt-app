"""HTTP layer only -- request/response translation, no business logic and no
direct database access (Section 5.1). Domain exceptions raised by
AuthService are translated to HTTP responses centrally in app/main.py."""

from fastapi import APIRouter, BackgroundTasks, Depends, status

from app.auth.deps import get_auth_service, get_current_user
from app.auth.models import User
from app.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenPair,
    UserRead,
    VerifyEmailRequest,
)
from app.auth.service import AuthService
from app.common.schemas import MessageResponse
from app.notifications.deps import get_notification_service
from app.notifications.service import NotificationService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    background_tasks: BackgroundTasks,
    auth_service: AuthService = Depends(get_auth_service),
    notifications: NotificationService = Depends(get_notification_service),
) -> User:
    user, token = await auth_service.register(payload.email, payload.password, payload.full_name)
    background_tasks.add_task(notifications.send_verification_email, user.email, token)
    return user


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    payload: VerifyEmailRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    await auth_service.verify_email(payload.token)
    return MessageResponse(message="Email verified successfully.")


@router.post("/login", response_model=TokenPair)
async def login(
    payload: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenPair:
    access_token, refresh_token = await auth_service.login(payload.email, payload.password)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenPair:
    access_token, refresh_token = await auth_service.refresh_access_token(payload.refresh_token)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> None:
    await auth_service.logout(payload.refresh_token)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    auth_service: AuthService = Depends(get_auth_service),
    notifications: NotificationService = Depends(get_notification_service),
) -> MessageResponse:
    result = await auth_service.request_password_reset(payload.email)
    if result is not None:
        user, token = result
        background_tasks.add_task(notifications.send_password_reset_email, user.email, token)

    # Identical response whether or not the email is registered (Section 7.1)
    return MessageResponse(
        message="If an account with that email exists, a reset link has been sent."
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    await auth_service.reset_password(payload.token, payload.new_password)
    return MessageResponse(message="Password reset successfully.")


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
