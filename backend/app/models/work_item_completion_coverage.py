from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WorkItemCompletionCoverage(Base):
    """Per-task cutover state and history-quality summary."""

    __tablename__ = "work_item_completion_coverage"
    __table_args__ = (
        CheckConstraint(
            "coverage_origin IN ('creation', 'migration')",
            name="ck_work_item_completion_coverage_origin",
        ),
        CheckConstraint(
            "legacy_status_event_count >= 0 AND "
            "legacy_completion_candidate_count >= 0 AND "
            "legacy_completion_imported_count >= 0 AND "
            "legacy_completion_omitted_count >= 0",
            name="ck_work_item_completion_coverage_counts_nonnegative",
        ),
        CheckConstraint(
            "assignment_event_count >= 0",
            name="ck_work_item_completion_coverage_assignment_event_count",
        ),
        CheckConstraint(
            "tracking_state_status IN ('open', 'in_progress', 'resolved', 'closed')",
            name="ck_work_item_completion_coverage_tracking_state_status",
        ),
    )

    work_item_id: Mapped[int] = mapped_column(
        ForeignKey("work_items.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    tracking_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # A coherent observable state at the boundary from which future
    # assignment/status events can be replayed. For migrated open tasks the
    # cycle start is deliberately unknown.
    tracking_state_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    tracking_state_status: Mapped[str] = mapped_column(String(20), nullable=False)
    tracking_state_assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_work_item_completion_coverage_tracking_state_assignee",
        ),
        nullable=True,
    )
    tracking_state_assignee_known: Mapped[bool] = mapped_column(
        Boolean, nullable=False
    )
    tracking_open_cycle_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    coverage_origin: Mapped[str] = mapped_column(String(20), nullable=False)
    captured_since_creation: Mapped[bool] = mapped_column(
        Boolean, nullable=False
    )
    legacy_status_event_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    legacy_completion_candidate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    legacy_completion_imported_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    legacy_completion_omitted_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    legacy_status_timestamps_ambiguous: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    legacy_status_timeline_inconsistent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    legacy_assignment_history_partial: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    legacy_assignment_timestamps_ambiguous: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    legacy_assignment_timeline_inconsistent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    assignment_event_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    assignment_sequence_reconstructible: Mapped[bool] = mapped_column(
        Boolean, nullable=False
    )
    assignment_timestamps_ambiguous: Mapped[bool] = mapped_column(
        Boolean, nullable=False
    )
    assignment_timeline_inconsistent: Mapped[bool] = mapped_column(
        Boolean, nullable=False
    )
