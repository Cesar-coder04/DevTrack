from datetime import datetime

from sqlalchemy import (
    Computed,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint(
            "_active_organization_id",
            "name",
            name="uq_projects_active_organization_name",
        ),
        UniqueConstraint(
            "_active_personal_owner_id",
            "name",
            name="uq_projects_active_personal_owner_name",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        nullable=False,
    )

    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    visibility: Mapped[str] = mapped_column(
        String(20),
        default="private",
        nullable=False,
        server_default="private",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    _active_organization_id: Mapped[int | None] = mapped_column(
        Integer,
        Computed(
            "CASE WHEN organization_id IS NOT NULL "
            "AND archived_at IS NULL AND deleted_at IS NULL "
            "THEN organization_id ELSE NULL END"
        ),
    )

    _active_personal_owner_id: Mapped[int | None] = mapped_column(
        Integer,
        Computed(
            "CASE WHEN organization_id IS NULL "
            "AND archived_at IS NULL AND deleted_at IS NULL "
            "THEN owner_id ELSE NULL END"
        ),
    )