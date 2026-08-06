"""Project table (Section 6.2) -- a grouping of tasks, owned by exactly one
user for this version (Section 20: multi-tenancy is out of scope)."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.mixins import Entity

if TYPE_CHECKING:
    from app.auth.models import User
    from app.tasks.models import Task


class Project(Entity):
    __tablename__ = "projects"
    __table_args__ = (
        Index(
            "ix_projects_owner_active",
            "owner_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    owner: Mapped["User"] = relationship(back_populates="projects")
    tasks: Mapped[list["Task"]] = relationship(back_populates="project")
