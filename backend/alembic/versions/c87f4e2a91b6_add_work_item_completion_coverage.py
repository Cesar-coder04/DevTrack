"""record per-task completion-history coverage

Revision ID: c87f4e2a91b6
Revises: f31c79a4e216

The downgrade removes only this revision's coverage metadata. That metadata
includes imported-legacy coverage diagnostics and would be lost on downgrade.
The conservative corrections to legacy completion snapshots remain in
work_item_completions after downgrade; original work_item_history rows are
never changed.
"""

from collections import defaultdict
from datetime import date, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c87f4e2a91b6"
down_revision: Union[str, Sequence[str], None] = "f31c79a4e216"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FINAL_STATUSES = {"resolved", "closed"}
ALL_STATUSES = {"open", "in_progress", *FINAL_STATUSES}


def _as_datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise TypeError("Unsupported legacy timestamp")


def _safe_snapshot_value(events, event_at, *, is_assignee, existing_user_ids):
    field_name = "assignee_id" if is_assignee else "due_date"
    matching = [row for row in events if row["field_name"] == field_name]
    if not matching:
        return None, False

    ordered = sorted(matching, key=lambda row: (row["changed_at"], row["id"]))
    if any(
        previous["changed_at"] == current["changed_at"]
        for previous, current in zip(ordered, ordered[1:])
    ):
        return None, False

    if any(
        previous["new_value"] != current["old_value"]
        for previous, current in zip(ordered, ordered[1:])
    ):
        return None, False

    if any(row["changed_at"] == event_at for row in ordered):
        return None, False

    previous = [row for row in ordered if row["changed_at"] < event_at]
    following = [row for row in ordered if row["changed_at"] > event_at]
    if previous:
        raw = previous[-1]["new_value"]
    elif following:
        raw = following[0]["old_value"]
    else:
        return None, False

    if raw is None:
        return None, True
    try:
        if is_assignee:
            user_id = int(raw)
            return (user_id, True) if user_id in existing_user_ids else (None, False)
        return date.fromisoformat(raw), True
    except (TypeError, ValueError):
        return None, False


def _status_timeline_diagnostics(events, current_status):
    status_events = sorted(
        (row for row in events if row["field_name"] == "status"),
        key=lambda row: (row["changed_at"], row["id"]),
    )
    ambiguous_timestamps = any(
        previous["changed_at"] == current["changed_at"]
        for previous, current in zip(status_events, status_events[1:])
    )
    invalid_values = any(
        row["old_value"] not in ALL_STATUSES
        or row["new_value"] not in ALL_STATUSES
        for row in status_events
    )
    broken_chain = any(
        previous["new_value"] != current["old_value"]
        for previous, current in zip(status_events, status_events[1:])
    )
    current_mismatch = bool(
        status_events and status_events[-1]["new_value"] != current_status
    )
    inconsistent = invalid_values or broken_chain or current_mismatch
    candidates = sum(
        row["old_value"] in ALL_STATUSES
        and row["new_value"] in FINAL_STATUSES
        and row["old_value"] not in FINAL_STATUSES
        for row in status_events
    )
    return (
        status_events,
        candidates,
        ambiguous_timestamps,
        inconsistent,
    )


def upgrade() -> None:
    coverage = op.create_table(
        "work_item_completion_coverage",
        sa.Column("work_item_id", sa.Integer(), nullable=False),
        sa.Column("tracking_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("coverage_origin", sa.String(length=20), nullable=False),
        sa.Column("captured_since_creation", sa.Boolean(), nullable=False),
        sa.Column("legacy_status_event_count", sa.Integer(), nullable=False),
        sa.Column("legacy_completion_candidate_count", sa.Integer(), nullable=False),
        sa.Column("legacy_completion_imported_count", sa.Integer(), nullable=False),
        sa.Column("legacy_completion_omitted_count", sa.Integer(), nullable=False),
        sa.Column("legacy_status_timestamps_ambiguous", sa.Boolean(), nullable=False),
        sa.Column("legacy_status_timeline_inconsistent", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "coverage_origin IN ('creation', 'migration')",
            name="ck_work_item_completion_coverage_origin",
        ),
        sa.CheckConstraint(
            "legacy_status_event_count >= 0 AND "
            "legacy_completion_candidate_count >= 0 AND "
            "legacy_completion_imported_count >= 0 AND "
            "legacy_completion_omitted_count >= 0",
            name="ck_work_item_completion_coverage_counts_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["work_item_id"], ["work_items.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("work_item_id"),
    )

    bind = op.get_bind()
    items = {
        row["id"]: row
        for row in bind.execute(
            sa.text("SELECT id, status FROM work_items WHERE type = 'task'")
        ).mappings()
    }
    baselines = {
        row["work_item_id"]: {
            **row,
            "baseline_at": _as_datetime(row["baseline_at"]),
        }
        for row in bind.execute(
            sa.text(
                "SELECT work_item_id, baseline_at FROM work_item_assignment_baselines"
            )
        ).mappings()
    }
    histories = [
        {**row, "changed_at": _as_datetime(row["changed_at"])}
        for row in bind.execute(
            sa.text(
                "SELECT id, work_item_id, field_name, old_value, new_value, changed_at "
                "FROM work_item_history ORDER BY work_item_id, changed_at, id"
            )
        ).mappings()
    ]
    histories_by_item = defaultdict(list)
    for row in histories:
        histories_by_item[row["work_item_id"]].append(row)

    completions = [
        row
        for row in bind.execute(
            sa.text(
                "SELECT id, work_item_id, source_history_id, completed_at "
                "FROM work_item_completions WHERE completed_at_is_utc = 0"
            )
        ).mappings()
    ]
    completion_by_item = defaultdict(list)
    for row in completions:
        completion_by_item[row["work_item_id"]].append(row)

    existing_user_ids = set(
        bind.execute(sa.text("SELECT id FROM users")).scalars().all()
    )
    for completion in completions:
        event_at = _as_datetime(completion["completed_at"])
        item_history = histories_by_item[completion["work_item_id"]]
        due_date, due_known = _safe_snapshot_value(
            item_history,
            event_at,
            is_assignee=False,
            existing_user_ids=existing_user_ids,
        )
        assignee_id, assignee_known = _safe_snapshot_value(
            item_history,
            event_at,
            is_assignee=True,
            existing_user_ids=existing_user_ids,
        )
        bind.execute(
            sa.text(
                "UPDATE work_item_completions SET "
                "due_date_at_completion = :due_date, due_date_known = :due_known, "
                "assignee_id_at_completion = :assignee_id, "
                "assignee_known = :assignee_known WHERE id = :id"
            ),
            {
                "due_date": due_date,
                "due_known": due_known,
                "assignee_id": assignee_id,
                "assignee_known": assignee_known,
                "id": completion["id"],
            },
        )

    rows = []
    for item_id, item in items.items():
        baseline = baselines.get(item_id)
        if baseline is None:
            raise RuntimeError(
                f"Task {item_id} has no assignment baseline; coverage cannot be asserted."
            )
        item_history = histories_by_item[item_id]
        status_events, candidate_count, ambiguous, inconsistent = (
            _status_timeline_diagnostics(item_history, item["status"])
        )
        imported_count = len(completion_by_item[item_id])
        rows.append(
            {
                "work_item_id": item_id,
                "tracking_started_at": baseline["baseline_at"],
                "coverage_origin": "migration",
                "captured_since_creation": False,
                "legacy_status_event_count": len(status_events),
                "legacy_completion_candidate_count": candidate_count,
                "legacy_completion_imported_count": imported_count,
                "legacy_completion_omitted_count": max(
                    candidate_count - imported_count, 0
                ),
                "legacy_status_timestamps_ambiguous": ambiguous,
                "legacy_status_timeline_inconsistent": inconsistent,
            }
        )
    if rows:
        bind.execute(coverage.insert(), rows)


def downgrade() -> None:
    op.drop_table("work_item_completion_coverage")
