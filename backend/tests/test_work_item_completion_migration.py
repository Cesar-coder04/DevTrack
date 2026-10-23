import importlib.util
from datetime import datetime
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
import pytest


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "f31c79a4e216_add_work_item_completions.py"
)
COVERAGE_MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "c87f4e2a91b6_add_work_item_completion_coverage.py"
)
TRACKING_STATE_MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "e91f8d2c7a34_add_work_item_tracking_state.py"
)


def load_migration():
    spec = importlib.util.spec_from_file_location(
        "work_item_completion_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_coverage_migration():
    spec = importlib.util.spec_from_file_location(
        "work_item_completion_coverage_migration", COVERAGE_MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_tracking_state_migration():
    spec = importlib.util.spec_from_file_location(
        "work_item_tracking_state_migration", TRACKING_STATE_MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_imports_only_verifiable_transitions_without_inventing_snapshots(
    monkeypatch,
):
    migration = load_migration()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE users (id INTEGER PRIMARY KEY)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE projects (id INTEGER PRIMARY KEY)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE work_items (id INTEGER PRIMARY KEY, type TEXT, "
                "status TEXT, project_id INTEGER, assigned_to_id INTEGER)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE work_item_history (id INTEGER PRIMARY KEY, "
                "work_item_id INTEGER, changed_by_id INTEGER, field_name TEXT, "
                "old_value TEXT, new_value TEXT, changed_at DATETIME)"
            )
            connection.execute(
                text("INSERT INTO users (id) VALUES (1), (2), (3)")
            )
            connection.execute(text("INSERT INTO projects (id) VALUES (7)"))
            connection.execute(
                text(
                    "INSERT INTO work_items "
                    "(id, type, status, project_id, assigned_to_id) VALUES "
                    "(1, 'task', 'closed', 7, 1), "
                    "(2, 'task', 'open', 7, NULL), "
                    "(3, 'task', 'closed', 7, 1), "
                    "(4, 'issue', 'resolved', 7, 1), "
                    "(5, 'task', 'closed', 7, 1), "
                    "(6, 'task', 'resolved', 7, 2), "
                    "(7, 'task', 'resolved', 7, 3), "
                    "(8, 'task', 'resolved', 7, 1)"
                )
            )
            history = [
                (1, 1, "assignee_id", None, "1", "2026-10-01 09:00:00"),
                (2, 1, "due_date", None, "2026-10-10", "2026-10-01 09:01:00"),
                (3, 1, "status", "open", "resolved", "2026-10-02 09:00:00"),
                (4, 1, "status", "resolved", "closed", "2026-10-03 09:00:00"),
                # Conflicting status timeline: do not choose an ordering.
                (5, 3, "status", "open", "resolved", "2026-10-04 09:00:00"),
                (6, 3, "status", "open", "closed", "2026-10-04 09:00:00"),
                (7, 4, "status", "open", "resolved", "2026-10-05 09:00:00"),
                # A clear completion, but no provable historical snapshots.
                (8, 5, "status", "in_progress", "closed", "2026-10-06 09:00:00"),
                (9, 6, "assignee_id", None, "1", "2026-10-06 08:00:00"),
                (10, 6, "assignee_id", "1", "2", "2026-10-06 08:00:00"),
                (11, 6, "due_date", None, "2026-10-20", "2026-10-06 08:00:00"),
                (12, 6, "due_date", "2026-10-20", "2026-10-21", "2026-10-06 08:00:00"),
                (13, 6, "status", "open", "resolved", "2026-10-07 09:00:00"),
                (14, 7, "assignee_id", None, "1", "2026-10-06 08:00:00"),
                (15, 7, "assignee_id", "2", "3", "2026-10-06 09:00:00"),
                (16, 7, "due_date", None, "2026-10-20", "2026-10-06 08:00:00"),
                (17, 7, "due_date", "2026-10-19", "2026-10-21", "2026-10-06 09:00:00"),
                (18, 7, "status", "open", "resolved", "2026-10-08 09:00:00"),
                (19, 8, "status", "open", "resolved", "2026-10-09 09:00:00"),
                (20, 8, "assignee_id", None, "1", "2026-10-10 09:00:00"),
                (21, 8, "due_date", None, "2026-10-20", "2026-10-10 09:00:00"),
            ]
            connection.execute(
                text(
                    "INSERT INTO work_item_history "
                    "(id, work_item_id, changed_by_id, field_name, old_value, "
                    "new_value, changed_at) VALUES "
                    "(:id, :item_id, 1, :field_name, :old_value, :new_value, "
                    ":changed_at)"
                ),
                [
                    {
                        "id": row[0],
                        "item_id": row[1],
                        "field_name": row[2],
                        "old_value": row[3],
                        "new_value": row[4],
                        "changed_at": row[5],
                    }
                    for row in history
                ],
            )

            operations = Operations(MigrationContext.configure(connection))
            monkeypatch.setattr(migration, "op", operations)
            migration.upgrade()

            baselines = connection.execute(
                text(
                    "SELECT work_item_id, assignee_id, baseline_kind "
                    "FROM work_item_assignment_baselines "
                    "ORDER BY work_item_id"
                )
            ).mappings().all()
            assert len(baselines) == 7
            assert all(row["baseline_kind"] == "migration" for row in baselines)
            assert [row["work_item_id"] for row in baselines] == [1, 2, 3, 5, 6, 7, 8]
            assert [row["assignee_id"] for row in baselines] == [1, None, 1, 1, 2, 3, 1]

            completions = connection.execute(
                text(
                    "SELECT work_item_id, source_history_id, status, "
                    "completed_at, completed_at_is_utc, "
                    "due_date_at_completion, due_date_known, "
                    "assignee_id_at_completion, assignee_known "
                    "FROM work_item_completions ORDER BY work_item_id"
                )
            ).mappings().all()

            assert len(completions) == 5
            known = completions[0]
            assert known["work_item_id"] == 1
            assert known["source_history_id"] == 3
            assert known["status"] == "resolved"
            assert datetime.fromisoformat(known["completed_at"]) == datetime(
                2026, 10, 2, 9
            )
            assert known["completed_at_is_utc"] in (0, False)
            assert known["due_date_at_completion"] == "2026-10-10"
            assert known["due_date_known"] in (1, True)
            assert known["assignee_id_at_completion"] == 1
            assert known["assignee_known"] in (1, True)

            unknown = completions[1]
            assert unknown["work_item_id"] == 5
            assert unknown["source_history_id"] == 8
            assert unknown["due_date_at_completion"] is None
            assert unknown["due_date_known"] in (0, False)
            assert unknown["assignee_id_at_completion"] is None
            assert unknown["assignee_known"] in (0, False)

            # A final current state without a transition, a conflicting
            # timeline, and an issue are not imported as task completions.
            assert {row["work_item_id"] for row in completions} == {1, 5, 6, 7, 8}

            coverage_migration = load_coverage_migration()
            monkeypatch.setattr(coverage_migration, "op", operations)
            coverage_migration.upgrade()
            coverage = connection.execute(
                text(
                    "SELECT work_item_id, coverage_origin, captured_since_creation, "
                    "legacy_status_event_count, legacy_completion_candidate_count, "
                    "legacy_completion_imported_count, legacy_completion_omitted_count, "
                    "legacy_status_timestamps_ambiguous, "
                    "legacy_status_timeline_inconsistent "
                    "FROM work_item_completion_coverage ORDER BY work_item_id"
                )
            ).mappings().all()
            assert len(coverage) == 7
            assert all(row["coverage_origin"] == "migration" for row in coverage)
            assert all(row["captured_since_creation"] in (0, False) for row in coverage)
            ambiguous = next(row for row in coverage if row["work_item_id"] == 3)
            assert ambiguous["legacy_status_timestamps_ambiguous"] in (1, True)
            assert ambiguous["legacy_completion_candidate_count"] == 2
            assert ambiguous["legacy_completion_imported_count"] == 0
            assert ambiguous["legacy_completion_omitted_count"] == 2
            no_status_history = next(
                row for row in coverage if row["work_item_id"] == 2
            )
            assert no_status_history["legacy_completion_imported_count"] == 0

            tracking_state_migration = load_tracking_state_migration()
            monkeypatch.setattr(tracking_state_migration, "op", operations)
            tracking_state_migration.upgrade()
            state_rows = connection.execute(
                text(
                    "SELECT work_item_id, tracking_state_at, tracking_state_status, "
                    "tracking_state_assignee_id, tracking_state_assignee_known, "
                    "tracking_open_cycle_started_at, "
                    "legacy_assignment_history_partial, "
                    "legacy_assignment_timestamps_ambiguous, "
                    "legacy_assignment_timeline_inconsistent, "
                    "assignment_event_count, assignment_sequence_reconstructible, "
                    "assignment_timestamps_ambiguous, "
                    "assignment_timeline_inconsistent "
                    "FROM work_item_completion_coverage ORDER BY work_item_id"
                )
            ).mappings().all()
            assert len(state_rows) == 7
            assert all(row["tracking_state_at"] is not None for row in state_rows)
            assert all(row["assignment_sequence_reconstructible"] in (1, True) for row in state_rows)
            assert all(row["assignment_event_count"] == 0 for row in state_rows)
            migrated_open = next(row for row in state_rows if row["work_item_id"] == 2)
            assert migrated_open["tracking_state_status"] == "open"
            assert migrated_open["tracking_state_assignee_id"] is None
            assert migrated_open["tracking_state_assignee_known"] in (1, True)
            assert migrated_open["tracking_open_cycle_started_at"] is None
            assert migrated_open["legacy_assignment_history_partial"] in (1, True)
            ambiguous_assignment = next(
                row for row in state_rows if row["work_item_id"] == 6
            )
            assert ambiguous_assignment["legacy_assignment_timestamps_ambiguous"] in (1, True)
            inconsistent_assignment = next(
                row for row in state_rows if row["work_item_id"] == 7
            )
            assert inconsistent_assignment["legacy_assignment_timeline_inconsistent"] in (1, True)

            tracking_state_migration.downgrade()
            assert "tracking_state_status" not in {
                column["name"]
                for column in inspect(connection).get_columns(
                    "work_item_completion_coverage"
                )
            }

            corrected = connection.execute(
                text(
                    "SELECT work_item_id, assignee_id_at_completion, assignee_known, "
                    "due_date_at_completion, due_date_known "
                    "FROM work_item_completions ORDER BY work_item_id"
                )
            ).mappings().all()
            tied_snapshot = next(row for row in corrected if row["work_item_id"] == 6)
            assert tied_snapshot["assignee_id_at_completion"] is None
            assert tied_snapshot["assignee_known"] in (0, False)
            assert tied_snapshot["due_date_at_completion"] is None
            assert tied_snapshot["due_date_known"] in (0, False)
            broken_chain_snapshot = next(
                row for row in corrected if row["work_item_id"] == 7
            )
            assert broken_chain_snapshot["assignee_known"] in (0, False)
            assert broken_chain_snapshot["due_date_known"] in (0, False)
            known_null_snapshot = next(
                row for row in corrected if row["work_item_id"] == 8
            )
            assert known_null_snapshot["assignee_id_at_completion"] is None
            assert known_null_snapshot["assignee_known"] in (1, True)
            assert known_null_snapshot["due_date_at_completion"] is None
            assert known_null_snapshot["due_date_known"] in (1, True)

            coverage_migration.downgrade()
            assert "work_item_completion_coverage" not in inspect(
                connection
            ).get_table_names()

            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(
                        text(
                            "INSERT INTO work_item_completions "
                            "(work_item_id, source_history_id, "
                            "project_id_at_completion, completed_at, "
                            "completed_at_is_utc, status, due_date_known, "
                            "assignee_known) VALUES "
                            "(1, 3, 7, '2026-10-02 09:00:00', 0, "
                            "'resolved', 0, 0)"
                        )
                    )

            migration.downgrade()
            assert "work_item_completions" not in inspect(connection).get_table_names()
            assert "work_item_assignment_baselines" not in inspect(
                connection
            ).get_table_names()
    finally:
        engine.dispose()


def test_safe_legacy_snapshots_reject_ties_and_broken_chains_but_keep_known_nulls():
    migration = load_coverage_migration()
    completion_at = datetime(2026, 10, 10, 12)
    before = datetime(2026, 10, 9, 12)
    after = datetime(2026, 10, 11, 12)

    tied_assignee = [
        {
            "id": 1,
            "field_name": "assignee_id",
            "old_value": None,
            "new_value": "1",
            "changed_at": before,
        },
        {
            "id": 2,
            "field_name": "assignee_id",
            "old_value": "1",
            "new_value": "2",
            "changed_at": before,
        },
    ]
    assert migration._safe_snapshot_value(
        tied_assignee,
        completion_at,
        is_assignee=True,
        existing_user_ids={1, 2},
    ) == (None, False)

    tied_due_date = [
        {
            "id": 3,
            "field_name": "due_date",
            "old_value": None,
            "new_value": "2026-10-12",
            "changed_at": before,
        },
        {
            "id": 4,
            "field_name": "due_date",
            "old_value": "2026-10-12",
            "new_value": "2026-10-13",
            "changed_at": before,
        },
    ]
    assert migration._safe_snapshot_value(
        tied_due_date,
        completion_at,
        is_assignee=False,
        existing_user_ids=set(),
    ) == (None, False)

    broken_chain = [
        {
            "id": 5,
            "field_name": "assignee_id",
            "old_value": None,
            "new_value": "1",
            "changed_at": before,
        },
        {
            "id": 6,
            "field_name": "assignee_id",
            "old_value": "2",
            "new_value": "3",
            "changed_at": after,
        },
    ]
    assert migration._safe_snapshot_value(
        broken_chain,
        completion_at,
        is_assignee=True,
        existing_user_ids={1, 2, 3},
    ) == (None, False)

    known_null = [
        {
            "id": 7,
            "field_name": "assignee_id",
            "old_value": None,
            "new_value": "1",
            "changed_at": after,
        }
    ]
    assert migration._safe_snapshot_value(
        known_null,
        completion_at,
        is_assignee=True,
        existing_user_ids={1},
    ) == (None, True)
    assert migration._safe_snapshot_value(
        [],
        completion_at,
        is_assignee=False,
        existing_user_ids=set(),
    ) == (None, False)


def test_tracking_state_migration_is_chained_and_revision_ids_are_unique():
    migration_files = list(TRACKING_STATE_MIGRATION_PATH.parent.glob("*.py"))
    revisions = {}
    for path in migration_files:
        text_source = path.read_text(encoding="utf-8")
        revision_match = __import__("re").search(
            r'^revision:\s*[^=]+?=\s*["\']([^"\']+)',
            text_source,
            __import__("re").MULTILINE,
        )
        if revision_match:
            revisions.setdefault(revision_match.group(1), []).append(path.name)
    assert all(len(paths) == 1 for paths in revisions.values())

    migration = load_tracking_state_migration()
    assert migration.down_revision == "c87f4e2a91b6"
