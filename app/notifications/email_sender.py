"""EmailSender interface and Gmail SMTP implementation (Section 12).

`EmailSender` is the seam: `NotificationService` (service.py) depends on
this Protocol, not on `GmailSMTPSender` directly, so the concrete provider
can be swapped for a transactional service (SES, Postmark, Resend) later
without touching any calling code -- Dependency Inversion applied to a real
integration point, per Section 12.
"""

import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class GmailSMTPSender:
    """Sends mail through a personal Gmail account via an App Password.

    Synchronous by design (`smtplib` has no async API) -- callers that care
    about not blocking the request on SMTP latency should invoke this via
    FastAPI `BackgroundTasks`, not `await` it directly.
    """

    def send(self, to: str, subject: str, body: str) -> None:
        settings = get_settings()

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = f"{settings.MAIL_FROM_NAME} <{settings.GMAIL_USER}>"
        message["To"] = to
        message.set_content(body)

        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(settings.GMAIL_USER, settings.GMAIL_APP_PASSWORD)
                server.send_message(message)
        except smtplib.SMTPException:
            # Never let an SMTP failure surface the account/app-password;
            # `logger.exception` here would include the message object in
            # some tracebacks, so we log a fixed, credential-free event.
            logger.error("email_send_failed", extra={"to": to, "subject": subject})
