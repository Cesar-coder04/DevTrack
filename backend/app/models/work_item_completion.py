from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
    true,
)
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WorkItemCompletion(Base):
    """Immutable snapshot of one task completion cycle."""

    __tablename__ = "work_item_completions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('resolved', 'closed')",
            name="ck_work_item_completions_status",
        ),
        UniqueConstraint(
            "source_history_id",
            name="uq_work_item_completions_source_history_id",
        ),
        Index(
            "ix_work_item_completions_assignee_completed_at",
            "assignee_id_at_completion",
            "completed_at",
        ),
        Index(
            "ix_work_item_completions_project_completed_at",
            "project_id_at_completion",
            "completed_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_item_id: Mapped[int] = mapped_column(
        ForeignKey("work_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_history_id: Mapped[int] = mapped_column(
        ForeignKey("work_item_history.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_id_at_completion: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assignee_id_at_completion: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    due_date_at_completion: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )
    # These flags distinguish a known NULL snapshot from unavailable legacy data.
    due_date_known: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    assignee_known: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    completed_at_is_utc: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )


def _reject_completion_mutation(_mapper, _connection, _target):
    raise InvalidRequestError("Work item completion records are immutable.")


event.listen(WorkItemCompletion, "before_update", _reject_completion_mutation)
event.listen(WorkItemCompletion, "before_delete", _reject_completion_mutation)
