"""capture a state baseline and assignment coverage for quarterly tracking

Revision ID: e91f8d2c7a34
Revises: c87f4e2a91b6
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e91f8d2c7a34"
down_revision: Union[str, Sequence[str], None] = "c87f4e2a91b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _as_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise TypeError("Unsupported assignment-history timestamp")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _assignment_diagnostics(events, baseline, current_assignee_id):
    ordered = sorted(events, key=lambda row: (row["changed_at"], row["id"]))
    ambiguous = any(
        previous["changed_at"] == current["changed_at"]
        for previous, current in zip(ordered, ordered[1:])
    )
    inconsistent = any(
        previous["new_value"] != current["old_value"]
        for previous, current in zip(ordered, ordered[1:])
    )

    baseline_at = baseline["baseline_at"] if baseline is not None else None
    baseline_value = (
        str(baseline["assignee_id"])
        if baseline is not None and baseline["assignee_id"] is not None
        else None
    )
    tracked = [
        row
        for row in ordered
        if baseline_at is not None and row["changed_at"] > baseline_at
    ]
    if baseline is None:
        inconsistent = True
    elif tracked:
        if tracked[0]["old_value"] != baseline_value:
            inconsistent = True
        if tracked[-1]["new_value"] != (
            str(current_assignee_id)
            if current_assignee_id is not None
            else None
        ):
            inconsistent = True
    elif baseline_value != (
        str(current_assignee_id) if current_assignee_id is not None else None
    ):
        inconsistent = True

    return ambiguous, inconsistent


def upgrade() -> None:
    op.add_column(
        "work_item_completion_coverage",
        sa.Column("tracking_state_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "work_item_completion_coverage",
        sa.Column("tracking_state_status", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "work_item_completion_coverage",
        sa.Column("tracking_state_assignee_id", sa.Integer(), nullable=True),
    )
    for column, column_type in (
        ("tracking_state_assignee_known", sa.Boolean()),
        ("legacy_assignment_history_partial", sa.Boolean()),
        ("legacy_assignment_timestamps_ambiguous", sa.Boolean()),
        ("legacy_assignment_timeline_inconsistent", sa.Boolean()),
        ("assignment_sequence_reconstructible", sa.Boolean()),
        ("assignment_timestamps_ambiguous", sa.Boolean()),
        ("assignment_timeline_inconsistent", sa.Boolean()),
    ):
        op.add_column(
            "work_item_completion_coverage",
            sa.Column(column, column_type, nullable=True),
        )
    op.add_column(
        "work_item_completion_coverage",
        sa.Column("tracking_open_cycle_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "work_item_completion_coverage",
        sa.Column("assignment_event_count", sa.Integer(), nullable=True),
    )

    bind = op.get_bind()
    # Freeze existing task rows while the migration establishes a common
    # observable status/assignee boundary. SQLite has no equivalent row lock;
    # production migrations should run with application writes paused as well.
    select_items = (
        "SELECT id, status, assigned_to_id FROM work_items "
        "WHERE type = 'task' ORDER BY id"
    )
    if bind.dialect.name == "mysql":
        select_items += " FOR UPDATE"
    items = bind.execute(sa.text(select_items)).mappings().all()
    cutoff = datetime.now(timezone.utc)

    histories = [
        {**row, "changed_at": _as_datetime(row["changed_at"])}
        for row in bind.execute(
            sa.text(
                "SELECT id, work_item_id, field_name, old_value, new_value, changed_at "
                "FROM work_item_history WHERE field_name = 'assignee_id' "
                "ORDER BY work_item_id, changed_at, id"
            )
        ).mappings()
    ]
    histories_by_item = defaultdict(list)
    for row in histories:
        histories_by_item[row["work_item_id"]].append(row)
    baselines = {
        row["work_item_id"]: {
            **row,
            "baseline_at": _as_datetime(row["baseline_at"]),
        }
        for row in bind.execute(
            sa.text(
                "SELECT work_item_id, assignee_id, baseline_at "
                "FROM work_item_assignment_baselines"
            )
        ).mappings()
    }

    updates = []
    for item in items:
        events = histories_by_item[item["id"]]
        baseline = baselines.get(item["id"])
        ambiguous, inconsistent = _assignment_diagnostics(
            events, baseline, item["assigned_to_id"]
        )
        updates.append(
            {
                "work_item_id": item["id"],
                "tracking_state_at": cutoff,
                "tracking_state_status": item["status"],
                "tracking_state_assignee_id": item["assigned_to_id"],
                "tracking_state_assignee_known": True,
                # An existing non-final task has an open cycle at the cut, but
                # its opening instant is not inferred from created_at/status.
                "tracking_open_cycle_started_at": None,
                "legacy_assignment_history_partial": True,
                "legacy_assignment_timestamps_ambiguous": ambiguous,
                "legacy_assignment_timeline_inconsistent": inconsistent,
                # The state snapshot is a known baseline for all subsequent
                # events, independently of the quality of earlier history.
                "assignment_event_count": 0,
                "assignment_sequence_reconstructible": True,
                "assignment_timestamps_ambiguous": False,
                "assignment_timeline_inconsistent": False,
            }
        )

    if updates:
        bind.execute(
            sa.text(
                "UPDATE work_item_completion_coverage SET "
                "tracking_state_at = :tracking_state_at, "
                "tracking_state_status = :tracking_state_status, "
                "tracking_state_assignee_id = :tracking_state_assignee_id, "
                "tracking_state_assignee_known = :tracking_state_assignee_known, "
                "tracking_open_cycle_started_at = :tracking_open_cycle_started_at, "
                "legacy_assignment_history_partial = :legacy_assignment_history_partial, "
                "legacy_assignment_timestamps_ambiguous = :legacy_assignment_timestamps_ambiguous, "
                "legacy_assignment_timeline_inconsistent = :legacy_assignment_timeline_inconsistent, "
                "assignment_event_count = :assignment_event_count, "
                "assignment_sequence_reconstructible = :assignment_sequence_reconstructible, "
                "assignment_timestamps_ambiguous = :assignment_timestamps_ambiguous, "
                "assignment_timeline_inconsistent = :assignment_timeline_inconsistent "
                "WHERE work_item_id = :work_item_id"
            ),
            updates,
        )

    with op.batch_alter_table("work_item_completion_coverage") as batch_op:
        batch_op.create_foreign_key(
            "fk_work_item_completion_coverage_tracking_state_assignee",
            "users",
            ["tracking_state_assignee_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        for column, column_type in (
            ("tracking_state_at", sa.DateTime(timezone=True)),
            ("tracking_state_status", sa.String(length=20)),
            ("tracking_state_assignee_known", sa.Boolean()),
            ("legacy_assignment_history_partial", sa.Boolean()),
            ("legacy_assignment_timestamps_ambiguous", sa.Boolean()),
            ("legacy_assignment_timeline_inconsistent", sa.Boolean()),
            ("assignment_event_count", sa.Integer()),
            ("assignment_sequence_reconstructible", sa.Boolean()),
            ("assignment_timestamps_ambiguous", sa.Boolean()),
            ("assignment_timeline_inconsistent", sa.Boolean()),
        ):
            batch_op.alter_column(
                column,
                existing_type=column_type,
                nullable=False,
            )
        batch_op.create_check_constraint(
            "ck_work_item_completion_coverage_assignment_event_count",
            "assignment_event_count >= 0",
        )
        batch_op.create_check_constraint(
            "ck_work_item_completion_coverage_tracking_state_status",
            "tracking_state_status IN ('open', 'in_progress', 'resolved', 'closed')",
        )


def downgrade() -> None:
    with op.batch_alter_table("work_item_completion_coverage") as batch_op:
        batch_op.drop_constraint(
            "ck_work_item_completion_coverage_assignment_event_count",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_work_item_completion_coverage_tracking_state_status",
            type_="check",
        )
        batch_op.drop_constraint(
            "fk_work_item_completion_coverage_tracking_state_assignee",
            type_="foreignkey",
        )
        for column in (
            "assignment_event_count",
            "assignment_timeline_inconsistent",
            "assignment_timestamps_ambiguous",
            "assignment_sequence_reconstructible",
            "legacy_assignment_timeline_inconsistent",
            "legacy_assignment_timestamps_ambiguous",
            "legacy_assignment_history_partial",
            "tracking_open_cycle_started_at",
            "tracking_state_assignee_known",
            "tracking_state_assignee_id",
            "tracking_state_status",
            "tracking_state_at",
        ):
            batch_op.drop_column(column)
