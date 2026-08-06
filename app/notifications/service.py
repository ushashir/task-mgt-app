"""Builds and sends the two auth-related emails (Section 7.1). Kept separate
from AuthService so the auth service layer never has to know how an email
gets built or delivered -- it only produces tokens; this module turns a
token into a message."""

from app.core.config import get_settings
from app.notifications.email_sender import EmailSender


class NotificationService:
    def __init__(self, email_sender: EmailSender) -> None:
        self._email_sender = email_sender

    def send_verification_email(self, to_email: str, token: str) -> None:
        settings = get_settings()
        link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        self._email_sender.send(
            to=to_email,
            subject="Verify your email",
            body=(
                "Welcome to Task Manager!\n\n"
                f"Please verify your email address by visiting:\n{link}\n\n"
                f"This link expires in {settings.EMAIL_VERIFICATION_TTL_HOURS} hours."
            ),
        )

    def send_password_reset_email(self, to_email: str, token: str) -> None:
        settings = get_settings()
        link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        self._email_sender.send(
            to=to_email,
            subject="Reset your password",
            body=(
                "A password reset was requested for your account.\n\n"
                f"Reset it by visiting:\n{link}\n\n"
                f"This link expires in {settings.PASSWORD_RESET_TTL_MINUTES} minutes. "
                "If you didn't request this, you can safely ignore this email."
            ),
        )
