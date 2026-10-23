from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session
from fastapi import HTTPException
from fastapi.testclient import TestClient
from types import SimpleNamespace

from app.db.base import Base
from app.api.deps import get_current_user
from app.db.session import get_db
from main import app
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.models.work_item import WorkItem
from app.models.work_item_assignment_baseline import WorkItemAssignmentBaseline
from app.models.work_item_completion import WorkItemCompletion
from app.models.work_item_completion_coverage import WorkItemCompletionCoverage
from app.models.work_item_history import WorkItemHistory
from app.schemas.dashboard_statistics import QuarterlyStatisticsResponse
from app.services.quarterly_statistics import (
    REPORT_TZ,
    calculate_quarterly_statistics,
    local_instant,
    quarter_dates,
    replay_assignee,
    replay_status,
)


@pytest.fixture
def statistics_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.create_function("CHAR_LENGTH", 1, len),
    )
    tables = [
        User.__table__, Organization.__table__, OrganizationMember.__table__,
        Project.__table__, ProjectMember.__table__, WorkItem.__table__,
        WorkItemHistory.__table__, WorkItemAssignmentBaseline.__table__,
        WorkItemCompletion.__table__,
        WorkItemCompletionCoverage.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as db:
        yield db
    engine.dispose()


def seed_personal_task(db, *, status="open", assignee_id=None, created_at=None):
    user = User(
        username="stats-user", email="stats@example.test", password_hash="x",
        display_name="Stats User",
    )
    db.add(user)
    db.flush()
    project = Project(name="Personal", owner_id=user.id)
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
    task = WorkItem(
        project_id=project.id, created_by_id=user.id, assigned_to_id=assignee_id,
        type="task", title="Task", status=status, priority="medium",
        created_at=created_at or datetime(2024, 12, 1, tzinfo=timezone.utc),
        updated_at=created_at or datetime(2024, 12, 1, tzinfo=timezone.utc),
    )
    db.add(task)
    db.flush()
    return user, project, task


def add_coverage(db, task, *, at, status="open", assignee=None, origin="creation"):
    db.add(
        WorkItemCompletionCoverage(
            work_item_id=task.id,
            tracking_started_at=at,
            tracking_state_at=at,
            tracking_state_status=status,
            tracking_state_assignee_id=assignee,
            tracking_state_assignee_known=True,
            tracking_open_cycle_started_at=at if status in {"open", "in_progress"} else None,
            coverage_origin=origin,
            captured_since_creation=origin == "creation",
            legacy_status_event_count=0,
            legacy_completion_candidate_count=0,
            legacy_completion_imported_count=0,
            legacy_completion_omitted_count=0,
            legacy_status_timestamps_ambiguous=False,
            legacy_status_timeline_inconsistent=False,
            legacy_assignment_history_partial=origin == "migration",
            legacy_assignment_timestamps_ambiguous=False,
            legacy_assignment_timeline_inconsistent=False,
            assignment_event_count=0,
            assignment_sequence_reconstructible=True,
            assignment_timestamps_ambiguous=False,
            assignment_timeline_inconsistent=False,
        )
    )


def test_natural_quarter_ranges_and_year_transition():
    assert quarter_dates(2025, 1) == (date(2025, 1, 1), date(2025, 4, 1))
    assert quarter_dates(2025, 2) == (date(2025, 4, 1), date(2025, 7, 1))
    assert quarter_dates(2025, 3) == (date(2025, 7, 1), date(2025, 10, 1))
    assert quarter_dates(2025, 4) == (date(2025, 10, 1), date(2026, 1, 1))
    with pytest.raises(ValueError):
        quarter_dates(2025, 5)


def test_madrid_date_and_iso_week_behavior_across_dst():
    assert local_instant(datetime(2025, 3, 30, 0, 30, tzinfo=timezone.utc)).date() == date(2025, 3, 30)
    assert local_instant(datetime(2025, 3, 30, 22, 30, tzinfo=timezone.utc)).date() == date(2025, 3, 31)
    # 30 March is Sunday; local ISO weeks begin on Monday.
    assert date(2025, 3, 30).weekday() == 6


def test_assignment_replay_distinguishes_known_null_unknown_and_ambiguity():
    baseline_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    coverage = SimpleNamespace(
        tracking_state_at=baseline_at,
        tracking_state_assignee_known=True,
        tracking_state_assignee_id=11,
    )
    event = SimpleNamespace(
        id=1, field_name="assignee_id", old_value="11", new_value=None,
        changed_at=datetime(2025, 2, 1, tzinfo=timezone.utc),
    )
    known_null = replay_assignee(coverage, [event], datetime(2025, 2, 2, tzinfo=timezone.utc))
    assert known_null == {"known": True, "assignee_id": None}
    unknown_coverage = SimpleNamespace(
        tracking_state_at=baseline_at,
        tracking_state_assignee_known=False,
        tracking_state_assignee_id=None,
    )
    assert replay_assignee(unknown_coverage, [], datetime(2025, 2, 2, tzinfo=timezone.utc))["known"] is False

    duplicate = SimpleNamespace(**{**event.__dict__, "id": 2})
    assert replay_assignee(
        coverage, [event, duplicate], datetime(2025, 2, 2, tzinfo=timezone.utc)
    )["known"] is False


def test_assignment_baseline_covers_known_null_before_tracking_state_cut(statistics_db):
    user, _, task = seed_personal_task(statistics_db, assignee_id=None)
    assignment_baseline_at = datetime(2024, 12, 31, 22, tzinfo=timezone.utc)
    state_cut = datetime(2025, 2, 1, tzinfo=timezone.utc)
    statistics_db.add(
        WorkItemAssignmentBaseline(
            work_item_id=task.id, assignee_id=user.id,
            baseline_at=assignment_baseline_at, baseline_kind="migration",
        )
    )
    add_coverage(
        statistics_db, task, at=state_cut, status="open", assignee=None,
        origin="migration",
    )
    statistics_db.add(
        WorkItemHistory(
            work_item_id=task.id, changed_by_id=user.id, field_name="assignee_id",
            old_value=str(user.id), new_value=None,
            changed_at=datetime(2025, 1, 15, tzinfo=timezone.utc),
        )
    )
    statistics_db.commit()

    result = calculate_quarterly_statistics(
        statistics_db, user_id=user.id, year=2025, quarter=1, scope="all"
    )
    assert result["coverage"]["assignments"] == "reliable"
    assert result["pending_unassigned"] == 1
    assert result["pending_assignee_unknown"] == 0

    assert result["period_complete"] is True

    final_week = result["weekly"][-1]
    assert final_week["pending_at_cut"] == 1
    assert final_week["required_per_week"] is None

def test_status_replay_marks_contradictory_chain_unavailable():
    baseline_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    coverage = SimpleNamespace(
        tracking_state_at=baseline_at, tracking_state_status="open",
        tracking_open_cycle_started_at=baseline_at,
    )
    contradictory = SimpleNamespace(
        id=1, field_name="status", old_value="resolved", new_value="closed",
        changed_at=datetime(2025, 2, 1, tzinfo=timezone.utc),
    )
    assert replay_status(
        coverage, [contradictory], datetime(2025, 2, 2, tzinfo=timezone.utc)
    )["known"] is False


def test_pending_cut_known_null_assignment_and_carry_in(statistics_db):
    user, _, task = seed_personal_task(statistics_db)
    add_coverage(
        statistics_db, task, at=datetime(2024, 12, 1, tzinfo=timezone.utc),
        status="open", assignee=None, origin="migration",
    )
    statistics_db.flush()
    statistics_db.get(WorkItemCompletionCoverage, task.id).tracking_open_cycle_started_at = None
    statistics_db.commit()

    result = calculate_quarterly_statistics(
        statistics_db, user_id=user.id, year=2025, quarter=1, scope="all"
    )
    assert QuarterlyStatisticsResponse.model_validate(result).quarter == 1
    assert result["pending_at_close"] == 1
    assert result["load"]["carried_in"] == 1
    assert result["pending_unassigned"] == 1
    assert result["pending_with_known_assignee"] == 0
    assert result["pending_assignee_unknown"] == 0


def test_completion_snapshot_drives_punctuality_and_resolved_to_closed_is_one(
    statistics_db,
):
    user, project, task = seed_personal_task(
        statistics_db, status="closed", created_at=datetime(2025, 1, 5, tzinfo=timezone.utc)
    )
    started = datetime(2025, 1, 5, tzinfo=timezone.utc)
    completed = datetime(2025, 2, 1, 12, tzinfo=timezone.utc)
    add_coverage(statistics_db, task, at=started, status="open")
    transition = WorkItemHistory(
        work_item_id=task.id, changed_by_id=user.id, field_name="status",
        old_value="open", new_value="resolved", changed_at=completed,
    )
    statistics_db.add(transition)
    statistics_db.flush()
    statistics_db.add(
        WorkItemCompletion(
            work_item_id=task.id, source_history_id=transition.id,
            project_id_at_completion=project.id, assignee_id_at_completion=None,
            completed_at=completed, completed_at_is_utc=True, status="resolved",
            due_date_at_completion=date(2025, 2, 1), due_date_known=True,
            assignee_known=True,
        )
    )
    statistics_db.add(
        WorkItemHistory(
            work_item_id=task.id, changed_by_id=user.id, field_name="status",
            old_value="resolved", new_value="closed",
            changed_at=datetime(2025, 2, 2, tzinfo=timezone.utc),
        )
    )
    statistics_db.commit()

    result = calculate_quarterly_statistics(
        statistics_db, user_id=user.id, year=2025, quarter=1, scope="all"
    )
    assert result["completed_cycles"] == 1
    assert result["completed_on_time_percent"] == 100.0
    assert result["punctuality_comparable_count"] == 1
    assert result["completed_unassigned"] == 1


def test_reopen_and_second_finalization_count_as_new_cycle(statistics_db):
    user, project, task = seed_personal_task(statistics_db, status="closed")
    baseline = datetime(2024, 12, 1, tzinfo=timezone.utc)
    add_coverage(statistics_db, task, at=baseline, status="open")
    transitions = [
        ("open", "resolved", datetime(2025, 2, 1, 12, tzinfo=timezone.utc)),
        ("resolved", "open", datetime(2025, 3, 1, 12, tzinfo=timezone.utc)),
        ("open", "closed", datetime(2025, 3, 5, 12, tzinfo=timezone.utc)),
    ]
    completion_events = []
    for old, new, at in transitions:
        history = WorkItemHistory(
            work_item_id=task.id, changed_by_id=user.id, field_name="status",
            old_value=old, new_value=new, changed_at=at,
        )
        statistics_db.add(history)
        statistics_db.flush()
        if new in {"resolved", "closed"} and old not in {"resolved", "closed"}:
            completion_events.append((history, at))
    for history, at in completion_events:
        statistics_db.add(
            WorkItemCompletion(
                work_item_id=task.id, source_history_id=history.id,
                project_id_at_completion=project.id, assignee_id_at_completion=None,
                completed_at=at, completed_at_is_utc=True, status=history.new_value,
                due_date_at_completion=None, due_date_known=True, assignee_known=True,
            )
        )
    statistics_db.commit()

    result = calculate_quarterly_statistics(
        statistics_db, user_id=user.id, year=2025, quarter=1, scope="all"
    )
    assert result["completed_cycles"] == 2
    assert result["pending_at_close"] == 0
    assert result["load"]["carried_in"] == 1
    assert result["load"]["new_cycles"] == 1
    assert result["total_cycles"] == 2
    assert result["completed_on_time_percent"] is None
    assert result["punctuality_comparable_count"] == 0


def test_unconfirmed_completion_timestamp_is_not_counted(statistics_db):
    user, project, task = seed_personal_task(statistics_db, status="resolved")
    at = datetime(2025, 2, 1, tzinfo=timezone.utc)
    add_coverage(statistics_db, task, at=datetime(2025, 1, 1, tzinfo=timezone.utc), status="open")
    history = WorkItemHistory(
        work_item_id=task.id, changed_by_id=user.id, field_name="status",
        old_value="open", new_value="resolved", changed_at=at,
    )
    statistics_db.add(history)
    statistics_db.flush()
    statistics_db.add(
        WorkItemCompletion(
            work_item_id=task.id, source_history_id=history.id,
            project_id_at_completion=project.id, assignee_id_at_completion=None,
            completed_at=at, completed_at_is_utc=False, status="resolved",
            due_date_at_completion=date(2025, 2, 1), due_date_known=True,
            assignee_known=True,
        )
    )
    statistics_db.commit()

    result = calculate_quarterly_statistics(
        statistics_db, user_id=user.id, year=2025, quarter=1, scope="all"
    )
    assert result["completed_cycles"] is None
    assert result["completed_on_time_percent"] is None
    assert result["punctuality_comparable_count"] is None
    assert result["coverage"]["completions"] == "partial"


def test_legacy_unconfirmed_completion_does_not_poison_tracked_quarter(statistics_db):
    user, project, task = seed_personal_task(statistics_db, status="resolved")
    cutoff = datetime(2024, 12, 31, tzinfo=timezone.utc)
    add_coverage(statistics_db, task, at=cutoff, status="resolved", origin="migration")
    statistics_db.flush()
    coverage = statistics_db.get(WorkItemCompletionCoverage, task.id)
    coverage.legacy_completion_imported_count = 1
    source = WorkItemHistory(
        work_item_id=task.id, changed_by_id=user.id, field_name="status",
        old_value="open", new_value="resolved",
        changed_at=datetime(2024, 12, 15, tzinfo=timezone.utc),
    )
    statistics_db.add(source)
    statistics_db.flush()
    statistics_db.add(
        WorkItemCompletion(
            work_item_id=task.id, source_history_id=source.id,
            project_id_at_completion=project.id, assignee_id_at_completion=None,
            completed_at=source.changed_at, completed_at_is_utc=False,
            status="resolved", due_date_at_completion=None,
            due_date_known=False, assignee_known=False,
        )
    )
    statistics_db.commit()

    result = calculate_quarterly_statistics(
        statistics_db, user_id=user.id, year=2025, quarter=1, scope="all"
    )
    assert result["completed_cycles"] == 0
    assert result["pending_at_close"] == 0
    assert result["coverage"]["completions"] == "reliable"


def test_future_quarter_is_rejected_before_data_access(statistics_db):
    from app.services.quarterly_statistics import calculate_quarterly_statistics

    now = datetime.now(timezone.utc).astimezone().date()
    future_year = now.year + 1
    with pytest.raises(HTTPException) as exc_info:
        calculate_quarterly_statistics(
            statistics_db, user_id=1, year=future_year, quarter=1, scope="all"
        )
    assert exc_info.value.status_code == 422


def test_missing_coverage_does_not_turn_pending_count_into_zero(statistics_db):
    user, project, _ = seed_personal_task(statistics_db)
    future_task = WorkItem(
        project_id=project.id, created_by_id=user.id, type="task",
        title="Created after the period", status="open", priority="medium",
        created_at=datetime(2025, 4, 1, tzinfo=timezone.utc),
        updated_at=datetime(2025, 4, 1, tzinfo=timezone.utc),
    )
    statistics_db.add(future_task)
    statistics_db.commit()

    result = calculate_quarterly_statistics(
        statistics_db, user_id=user.id, year=2025, quarter=1, scope="all"
    )
    assert result["pending_at_close"] is None
    assert result["total_cycles"] is None
    assert result["coverage"]["state_and_cycles"] == "unavailable"
    assert any(warning["code"] == "coverage_snapshot_missing" for warning in result["warnings"])


def test_empty_current_quarter_returns_zero_metrics_and_future_weeks(statistics_db):
    user = User(
        username="empty-current", email="empty-current@example.test",
        password_hash="x", display_name="Empty Current",
    )
    statistics_db.add(user)
    statistics_db.flush()
    project = Project(name="Empty current project", owner_id=user.id)
    statistics_db.add(project)
    statistics_db.flush()
    statistics_db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
    statistics_db.commit()

    now_local = datetime.now(timezone.utc).astimezone(REPORT_TZ)
    quarter = (now_local.month - 1) // 3 + 1
    result = calculate_quarterly_statistics(
        statistics_db, user_id=user.id, year=now_local.year,
        quarter=quarter, scope="all",
    )

    assert result["period_complete"] is False
    assert result["total_cycles"] == 0
    assert result["completed_cycles"] == 0
    assert result["pending_at_close"] == 0
    assert result["load"] == {"carried_in": 0, "new_cycles": 0}
    assert result["coverage"] == {
        "state_and_cycles": "reliable", "assignments": "reliable",
        "completions": "reliable", "due_date_snapshots": "reliable",
    }
    future_points = [point for point in result["weekly"] if point["week_start"] > now_local.date()]
    assert future_points
    assert all(
        point["completed_cumulative"] is None
        and point["pending_at_cut"] is None
        and point["required_cumulative"] is None
        and point["required_per_week"] is None
        and point["coverage"] == "unavailable"
        for point in future_points
    )
    assert QuarterlyStatisticsResponse.model_validate(result)


def test_past_quarter_with_only_later_created_tasks_is_reliable_zero(statistics_db):
    user, project, _ = seed_personal_task(
        statistics_db, created_at=datetime(2025, 4, 1, tzinfo=timezone.utc)
    )
    statistics_db.commit()

    result = calculate_quarterly_statistics(
        statistics_db, user_id=user.id, year=2025, quarter=1, scope="all"
    )

    assert result["total_cycles"] == 0
    assert result["completed_cycles"] == 0
    assert result["pending_at_close"] == 0
    assert result["load"] == {"carried_in": 0, "new_cycles": 0}
    assert result["coverage"]["state_and_cycles"] == "reliable"
    assert result["coverage"]["completions"] == "reliable"
    assert not any(
        warning["code"] == "coverage_snapshot_missing"
        for warning in result["warnings"]
    )
    assert QuarterlyStatisticsResponse.model_validate(result)


def test_past_quarter_with_no_tasks_returns_zero_metrics(statistics_db):
    user = User(
        username="empty-past", email="empty-past@example.test",
        password_hash="x", display_name="Empty Past",
    )
    statistics_db.add(user)
    statistics_db.flush()
    project = Project(name="Empty past project", owner_id=user.id)
    statistics_db.add(project)
    statistics_db.flush()
    statistics_db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
    statistics_db.commit()

    result = calculate_quarterly_statistics(
        statistics_db, user_id=user.id, year=2020, quarter=2, scope="all"
    )

    assert result["period_complete"] is True
    assert result["total_cycles"] == 0
    assert result["completed_cycles"] == 0
    assert result["pending_at_close"] == 0
    assert result["load"] == {"carried_in": 0, "new_cycles": 0}
    assert all(point["completed_cumulative"] == 0 for point in result["weekly"])
    assert QuarterlyStatisticsResponse.model_validate(result)


def test_unknown_cycle_at_quarter_start_makes_load_split_incomplete(statistics_db):
    user, project, task = seed_personal_task(statistics_db, status="resolved")
    tracking_start = datetime(2024, 12, 1, tzinfo=timezone.utc)
    snapshot_at = datetime(2025, 2, 1, tzinfo=timezone.utc)
    completion_at = datetime(2025, 3, 1, 12, tzinfo=timezone.utc)
    add_coverage(
        statistics_db, task, at=tracking_start, status="open", origin="migration"
    )
    statistics_db.flush()
    coverage = statistics_db.get(WorkItemCompletionCoverage, task.id)
    coverage.tracking_state_at = snapshot_at
    coverage.tracking_state_status = "open"
    coverage.tracking_open_cycle_started_at = None
    transition = WorkItemHistory(
        work_item_id=task.id, changed_by_id=user.id, field_name="status",
        old_value="open", new_value="resolved", changed_at=completion_at,
    )
    statistics_db.add(transition)
    statistics_db.flush()
    statistics_db.add(
        WorkItemCompletion(
            work_item_id=task.id, source_history_id=transition.id,
            project_id_at_completion=project.id, assignee_id_at_completion=None,
            completed_at=completion_at, completed_at_is_utc=True,
            status="resolved", due_date_at_completion=None,
            due_date_known=True, assignee_known=True,
        )
    )
    statistics_db.commit()

    result = calculate_quarterly_statistics(
        statistics_db, user_id=user.id, year=2025, quarter=1, scope="all"
    )

    assert result["completed_cycles"] == 1
    assert result["pending_at_close"] == 0
    assert result["total_cycles"] == 1
    assert result["load"]["carried_in"] is None
    assert result["load"]["new_cycles"] is None
    assert result["coverage"]["state_and_cycles"] == "partial"
    assert QuarterlyStatisticsResponse.model_validate(result)


def test_organization_and_project_scopes_preserve_membership_checks(statistics_db):
    user = User(
        username="scope-member", email="scope-member@example.test",
        password_hash="x", display_name="Scope Member",
    )
    outsider = User(
        username="scope-outsider", email="scope-outsider@example.test",
        password_hash="x", display_name="Scope Outsider",
    )
    statistics_db.add_all([user, outsider])
    statistics_db.flush()
    organization = Organization(name="Scoped org", slug="scoped-org", owner_id=user.id)
    statistics_db.add(organization)
    statistics_db.flush()
    statistics_db.add(
        OrganizationMember(organization_id=organization.id, user_id=user.id, role="owner")
    )
    accessible_project = Project(
        name="Accessible org project", owner_id=user.id,
        organization_id=organization.id,
    )
    inaccessible_project = Project(
        name="Project without membership", owner_id=user.id,
        organization_id=organization.id,
    )
    statistics_db.add_all([accessible_project, inaccessible_project])
    statistics_db.flush()
    statistics_db.add(
        ProjectMember(project_id=accessible_project.id, user_id=user.id, role="member")
    )
    statistics_db.add(
        ProjectMember(project_id=inaccessible_project.id, user_id=outsider.id, role="member")
    )
    statistics_db.commit()

    organization_result = calculate_quarterly_statistics(
        statistics_db, user_id=user.id, year=2025, quarter=1,
        scope="organization", organization_id=organization.id,
    )
    assert organization_result["scope"] == "organization"
    assert QuarterlyStatisticsResponse.model_validate(organization_result)

    project_result = calculate_quarterly_statistics(
        statistics_db, user_id=user.id, year=2025, quarter=1,
        scope="project", project_id=accessible_project.id,
    )
    assert project_result["scope"] == "project"
    assert project_result["project_id"] == accessible_project.id
    assert QuarterlyStatisticsResponse.model_validate(project_result)

    with pytest.raises(HTTPException) as no_organization_access:
        calculate_quarterly_statistics(
            statistics_db, user_id=outsider.id, year=2025, quarter=1,
            scope="organization", organization_id=organization.id,
        )
    assert no_organization_access.value.status_code == 403

    with pytest.raises(HTTPException) as no_project_access:
        calculate_quarterly_statistics(
            statistics_db, user_id=user.id, year=2025, quarter=1,
            scope="project", project_id=inaccessible_project.id,
        )
    assert no_project_access.value.status_code == 403

    with pytest.raises(HTTPException) as project_member_without_org_access:
        calculate_quarterly_statistics(
            statistics_db, user_id=outsider.id, year=2025, quarter=1,
            scope="project", project_id=inaccessible_project.id,
        )
    assert project_member_without_org_access.value.status_code == 403


def test_organization_scope_requires_organization_membership(statistics_db):
    user = User(
        username="org-user", email="org@example.test", password_hash="x",
        display_name="Org User",
    )
    other = User(
        username="other-user", email="other@example.test", password_hash="x",
        display_name="Other User",
    )
    statistics_db.add_all([user, other])
    statistics_db.flush()
    org = Organization(name="Org", slug="org", owner_id=user.id)
    statistics_db.add(org)
    statistics_db.flush()
    project = Project(name="Org project", owner_id=user.id, organization_id=org.id)
    statistics_db.add(project)
    statistics_db.flush()
    statistics_db.add(ProjectMember(project_id=project.id, user_id=user.id, role="member"))
    statistics_db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role="owner"))
    statistics_db.commit()

    accessible = calculate_quarterly_statistics(
        statistics_db, user_id=user.id, year=2025, quarter=1, scope="all"
    )
    assert accessible["total_cycles"] == 0
    with pytest.raises(HTTPException) as denied:
        calculate_quarterly_statistics(
            statistics_db, user_id=other.id, year=2025, quarter=1,
            scope="organization", organization_id=org.id,
        )
    assert denied.value.status_code == 403
    task = WorkItem(
        project_id=project.id, created_by_id=user.id, type="task", title="Org task",
        status="open", priority="medium",
    )
    statistics_db.add(task)
    statistics_db.flush()
    org.deleted_at = datetime.now(timezone.utc)
    statistics_db.commit()
    after_org_deletion = calculate_quarterly_statistics(
        statistics_db, user_id=user.id, year=2025, quarter=1, scope="all"
    )
    assert after_org_deletion["total_cycles"] == 0
    assert statistics_db.get(WorkItem, task.id) is not None

    with pytest.raises(HTTPException) as exc_info:
        calculate_quarterly_statistics(
            statistics_db, user_id=other.id, year=2025, quarter=1,
            scope="organization", organization_id=org.id,
        )
    assert exc_info.value.status_code == 404


def test_statistics_endpoint_requires_session_and_valid_scope():
    def override_db():
        yield object()

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            unauthenticated = client.get(
                "/users/me/dashboard/statistics?year=2025&quarter=1"
            )
        assert unauthenticated.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    try:
        with TestClient(app) as client:
            invalid_scope = client.get(
                "/users/me/dashboard/statistics?scope=organization&year=2025&quarter=1"
            )
        assert invalid_scope.status_code == 422
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_statistics_endpoint_returns_validated_service_contract(statistics_db):
    user, _, task = seed_personal_task(statistics_db)
    add_coverage(
        statistics_db, task, at=datetime(2024, 12, 1, tzinfo=timezone.utc),
        status="open", assignee=None,
    )
    statistics_db.commit()

    def override_db():
        yield statistics_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user.id)
    try:
        with TestClient(app) as client:
            response = client.get(
                "/users/me/dashboard/statistics?year=2025&quarter=1&scope=personal"
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["completed_cycles"] == 0
        assert payload["pending_at_close"] == 1
        assert payload["pending_unassigned"] == 1
        assert payload["coverage"]["state_and_cycles"] == "reliable"
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
