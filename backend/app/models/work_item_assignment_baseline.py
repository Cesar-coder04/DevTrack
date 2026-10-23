from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WorkItemAssignmentBaseline(Base):
    """Known assignee state at task creation or historical cutover."""

    __tablename__ = "work_item_assignment_baselines"
    __table_args__ = (
        CheckConstraint(
            "baseline_kind IN ('creation', 'migration')",
            name="ck_work_item_assignment_baselines_kind",
        ),
        Index(
            "ix_work_item_assignment_baselines_assignee_id",
            "assignee_id",
        ),
    )

    work_item_id: Mapped[int] = mapped_column(
        ForeignKey("work_items.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    baseline_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    baseline_kind: Mapped[str] = mapped_column(String(20), nullable=False)
