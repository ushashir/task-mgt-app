from functools import lru_cache

from app.notifications.email_sender import EmailSender, GmailSMTPSender
from app.notifications.service import NotificationService


@lru_cache
def get_email_sender() -> EmailSender:
    return GmailSMTPSender()


def get_notification_service() -> NotificationService:
    return NotificationService(get_email_sender())
