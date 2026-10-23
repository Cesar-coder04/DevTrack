"""add immutable work item completion snapshots

Revision ID: f31c79a4e216
Revises: a34c7e91b2d0
Create Date: 2026-10-22

Only status timelines that are internally consistent and have unambiguous
timestamps are imported. Legacy snapshot values that cannot be proven remain
unknown; legacy timestamps are preserved but are not asserted to be UTC.
"""

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f31c79a4e216"
down_revision: Union[str, Sequence[str], None] = "a34c7e91b2d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FINAL_STATUSES = {"resolved", "closed"}
ALL_STATUSES = {"open", "in_progress", *FINAL_STATUSES}


def _snapshot_value(events, event_at, *, is_assignee, existing_user_ids):
    """Return a provable value at event_at, or (None, False)."""
    matching = [
        row
        for row in events
        if row["field_name"] in ({"assignee_id"} if is_assignee else {"due_date"})
    ]
    same_time = [row for row in matching if row["changed_at"] == event_at]
    if same_time:
        return None, False

    previous = [row for row in matching if row["changed_at"] < event_at]
    following = [row for row in matching if row["changed_at"] > event_at]
    if previous:
        raw = max(previous, key=lambda row: (row["changed_at"], row["id"]))[
            "new_value"
        ]
    elif following:
        raw = min(following, key=lambda row: (row["changed_at"], row["id"]))[
            "old_value"
        ]
    else:
        return None, False

    if raw is None:
        return None, True
    try:
        if is_assignee:
            user_id = int(raw)
            return (
                (user_id, True)
                if user_id in existing_user_ids
                else (None, False)
            )
        return date.fromisoformat(raw), True
    except (TypeError, ValueError):
        return None, False


def _as_datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise TypeError("Unsupported legacy timestamp")


def _backfill_verified_transitions(completions):
    bind = op.get_bind()
    items = {
        row["id"]: row
        for row in bind.execute(
            sa.text(
                "SELECT id, type, status, project_id FROM work_items"
            )
        ).mappings()
    }
    existing_user_ids = set(
        bind.execute(sa.text("SELECT id FROM users")).scalars().all()
    )
    histories = [
        {**row, "changed_at": _as_datetime(row["changed_at"])}
        for row in bind.execute(
            sa.text(
                "SELECT id, work_item_id, field_name, old_value, new_value, "
                "changed_at FROM work_item_history "
                "ORDER BY work_item_id, changed_at, id"
            )
        ).mappings()
    ]
    by_item = defaultdict(list)
    for row in histories:
        by_item[row["work_item_id"]].append(row)

    rows_to_insert = []
    for item_id, item_histories in by_item.items():
        item = items.get(item_id)
        if item is None or item["type"] != "task":
            continue

        status_events = [
            row for row in item_histories if row["field_name"] == "status"
        ]
        if not status_events:
            continue

        # MySQL DATETIME may have second precision. A tied timeline cannot be
        # ordered reliably from the legacy rows, even with an ID tiebreaker.
        status_times = [row["changed_at"] for row in status_events]
        if len(status_times) != len(set(status_times)):
            continue

        timeline_is_consistent = all(
            row["old_value"] in ALL_STATUSES
            and row["new_value"] in ALL_STATUSES
            and (
                index == 0
                or status_events[index - 1]["new_value"] == row["old_value"]
            )
            for index, row in enumerate(status_events)
        )
        if not timeline_is_consistent or item["status"] != status_events[-1]["new_value"]:
            continue

        for transition in status_events:
            if (
                transition["old_value"] in FINAL_STATUSES
                or transition["new_value"] not in FINAL_STATUSES
            ):
                continue

            due_date, due_known = _snapshot_value(
                item_histories,
                transition["changed_at"],
                is_assignee=False,
                existing_user_ids=existing_user_ids,
            )
            assignee_id, assignee_known = _snapshot_value(
                item_histories,
                transition["changed_at"],
                is_assignee=True,
                existing_user_ids=existing_user_ids,
            )
            rows_to_insert.append(
                {
                    "work_item_id": item_id,
                    "source_history_id": transition["id"],
                    "project_id_at_completion": item["project_id"],
                    "assignee_id_at_completion": assignee_id,
                    "completed_at": transition["changed_at"],
                    "completed_at_is_utc": False,
                    "status": transition["new_value"],
                    "due_date_at_completion": due_date,
                    "due_date_known": due_known,
                    "assignee_known": assignee_known,
                }
            )

    if rows_to_insert:
        bind.execute(completions.insert(), rows_to_insert)


def _backfill_assignment_baselines(baselines):
    bind = op.get_bind()
    cutoff = datetime.now(timezone.utc)
    rows = [
        {
            "work_item_id": row["id"],
            "assignee_id": row["assigned_to_id"],
            "baseline_at": cutoff,
            "baseline_kind": "migration",
        }
        for row in bind.execute(
            sa.text(
                "SELECT id, assigned_to_id FROM work_items WHERE type = 'task'"
            )
        ).mappings()
    ]
    if rows:
        bind.execute(baselines.insert(), rows)


def upgrade() -> None:
    baselines = op.create_table(
        "work_item_assignment_baselines",
        sa.Column("work_item_id", sa.Integer(), nullable=False),
        sa.Column("assignee_id", sa.Integer(), nullable=True),
        sa.Column("baseline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("baseline_kind", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "baseline_kind IN ('creation', 'migration')",
            name="ck_work_item_assignment_baselines_kind",
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["work_item_id"], ["work_items.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("work_item_id"),
    )
    op.create_index(
        "ix_work_item_assignment_baselines_assignee_id",
        "work_item_assignment_baselines",
        ["assignee_id"],
    )
    _backfill_assignment_baselines(baselines)

    completions = op.create_table(
        "work_item_completions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("work_item_id", sa.Integer(), nullable=False),
        sa.Column("source_history_id", sa.Integer(), nullable=False),
        sa.Column("project_id_at_completion", sa.Integer(), nullable=False),
        sa.Column("assignee_id_at_completion", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "completed_at_is_utc",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("due_date_at_completion", sa.Date(), nullable=True),
        sa.Column(
            "due_date_known", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "assignee_known", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.CheckConstraint(
            "status IN ('resolved', 'closed')",
            name="ck_work_item_completions_status",
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id_at_completion"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["project_id_at_completion"], ["projects.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_history_id"], ["work_item_history.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["work_item_id"], ["work_items.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_history_id",
            name="uq_work_item_completions_source_history_id",
        ),
    )
    op.create_index(
        "ix_work_item_completions_work_item_id",
        "work_item_completions",
        ["work_item_id"],
    )
    op.create_index(
        "ix_work_item_completions_assignee_completed_at",
        "work_item_completions",
        ["assignee_id_at_completion", "completed_at"],
    )
    op.create_index(
        "ix_work_item_completions_project_completed_at",
        "work_item_completions",
        ["project_id_at_completion", "completed_at"],
    )
    _backfill_verified_transitions(completions)


def downgrade() -> None:
    op.drop_index(
        "ix_work_item_completions_project_completed_at",
        table_name="work_item_completions",
    )
    op.drop_index(
        "ix_work_item_completions_assignee_completed_at",
        table_name="work_item_completions",
    )
    op.drop_index(
        "ix_work_item_completions_work_item_id",
        table_name="work_item_completions",
    )
    op.drop_table("work_item_completions")
    op.drop_index(
        "ix_work_item_assignment_baselines_assignee_id",
        table_name="work_item_assignment_baselines",
    )
    op.drop_table("work_item_assignment_baselines")
