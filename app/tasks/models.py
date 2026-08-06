"""Task table and enums (Section 6.2)."""

import uuid
from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.mixins import Entity

if TYPE_CHECKING:
    from app.projects.models import Project


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Task(Entity):
    __tablename__ = "tasks"
    __table_args__ = (
        # The filter every list-tasks query applies first (Section 6.2).
        Index(
            "ix_tasks_project_status_active",
            "project_id",
            "status",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(
            TaskStatus,
            name="task_status",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        default=TaskStatus.TODO,
        nullable=False,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        SAEnum(
            TaskPriority,
            name="task_priority",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        default=TaskPriority.MEDIUM,
        nullable=False,
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="tasks")
