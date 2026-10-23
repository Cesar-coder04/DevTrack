"""Quarterly task statistics with explicit uncertainty propagation."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.work_item import WorkItem
from app.models.work_item_assignment_baseline import WorkItemAssignmentBaseline
from app.models.work_item_completion import WorkItemCompletion
from app.models.work_item_completion_coverage import WorkItemCompletionCoverage
from app.models.work_item_history import WorkItemHistory

REPORT_TZ = ZoneInfo("Europe/Madrid")
FINAL = frozenset({"resolved", "closed"})
NON_FINAL = frozenset({"open", "in_progress"})
VALID_STATUSES = FINAL | NON_FINAL


def quarter_dates(year: int, quarter: int) -> tuple[date, date]:
    """Return half-open local calendar bounds for a natural quarter."""
    if year < 1900 or year > 9998:
        raise ValueError("year must be between 1900 and 9998")
    if quarter not in (1, 2, 3, 4):
        raise ValueError("quarter must be between 1 and 4")
    month = (quarter - 1) * 3 + 1
    start = date(year, month, 1)
    if quarter == 4:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 3, 1)
    return start, end


def as_utc(value: datetime) -> datetime:
    # Per the tracking policy these DateTime columns are UTC by write contract.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def local_instant(value: datetime) -> datetime:
    return as_utc(value).astimezone(REPORT_TZ)


def parse_assignee(raw: str | None) -> tuple[int | None, bool]:
    if raw is None:
        return None, True
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return None, False
    return (parsed, True) if parsed > 0 else (None, False)


def _status_events(events: list[WorkItemHistory]) -> list[WorkItemHistory]:
    return sorted(
        (event for event in events if event.field_name == "status"),
        key=lambda event: (as_utc(event.changed_at), event.id),
    )


def replay_status(
    coverage: WorkItemCompletionCoverage | None,
    events: list[WorkItemHistory],
    at: datetime,
) -> dict:
    """Reconstruct state at an instant only from a known baseline and chain."""
    if coverage is None:
        return {"known": False, "active": None, "opened_at": None, "status": None}
    baseline_at = as_utc(coverage.tracking_state_at)
    if baseline_at > at:
        return {"known": False, "active": None, "opened_at": None, "status": None}
    state = coverage.tracking_state_status
    if state not in VALID_STATUSES:
        return {"known": False, "active": None, "opened_at": None, "status": None}
    active = state in NON_FINAL
    opened_at = (
        as_utc(coverage.tracking_open_cycle_started_at)
        if coverage.tracking_open_cycle_started_at is not None
        else None
    )
    previous = state
    timeline = _status_events(events)
    post = [
        event for event in timeline
        if baseline_at < as_utc(event.changed_at) <= at
    ]
    times = [as_utc(event.changed_at) for event in post]
    if len(times) != len(set(times)):
        return {"known": False, "active": None, "opened_at": None, "status": None}
    for event in post:
        event_at = as_utc(event.changed_at)
        if event.old_value not in VALID_STATUSES or event.new_value not in VALID_STATUSES:
            return {"known": False, "active": None, "opened_at": None, "status": None}
        if event.old_value != previous:
            return {"known": False, "active": None, "opened_at": None, "status": None}
        was_active = previous in NON_FINAL
        is_active = event.new_value in NON_FINAL
        if not was_active and is_active:
            opened_at = event_at
        elif was_active and not is_active:
            opened_at = None
        # resolved -> closed remains final and does not create a new cycle.
        previous = event.new_value
        active = is_active
    return {"known": True, "active": active, "opened_at": opened_at, "status": previous}


def replay_assignee(
    coverage: WorkItemCompletionCoverage | None,
    events: list[WorkItemHistory],
    at: datetime,
    baseline: WorkItemAssignmentBaseline | None = None,
) -> dict:
    tracking_at = as_utc(coverage.tracking_state_at) if coverage is not None else None
    if coverage is not None and tracking_at is not None and tracking_at <= at:
        if not coverage.tracking_state_assignee_known:
            return {"known": False, "assignee_id": None}
        baseline_at = tracking_at
        value = coverage.tracking_state_assignee_id
    elif baseline is not None and as_utc(baseline.baseline_at) <= at:
        baseline_at = as_utc(baseline.baseline_at)
        value = baseline.assignee_id
    else:
        return {"known": False, "assignee_id": None}
    previous_raw = str(value) if value is not None else None
    timeline = sorted(
        (event for event in events if event.field_name == "assignee_id"),
        key=lambda event: (as_utc(event.changed_at), event.id),
    )
    post = [
        event for event in timeline
        if baseline_at < as_utc(event.changed_at) <= at
    ]
    times = [as_utc(event.changed_at) for event in post]
    if len(times) != len(set(times)):
        return {"known": False, "assignee_id": None}
    for event in post:
        next_value, valid = parse_assignee(event.new_value)
        old_value, old_valid = parse_assignee(event.old_value)
        if not valid or not old_valid or event.old_value != previous_raw:
            return {"known": False, "assignee_id": None}
        value = next_value
        previous_raw = event.new_value
    return {"known": True, "assignee_id": value}


def _status_dimension(coverage, histories, period_start, period_end):
    # Old intervals before the tracking cut are intentionally not inferred.
    if coverage is None:
        return "unavailable"
    snapshot = as_utc(coverage.tracking_state_at)
    if snapshot > period_end:
        return "unavailable"
    if snapshot > period_start:
        if (
            coverage.coverage_origin == "creation"
            and as_utc(coverage.tracking_started_at) < period_end
        ):
            result = replay_status(coverage, histories, period_end)
            return "reliable" if result["known"] else "partial"
        return "partial"
    result = replay_status(coverage, histories, period_end)
    return "reliable" if result["known"] else "partial"


def _assignment_dimension(coverage, histories, period_start, period_end, baseline=None):
    if coverage is None:
        return "unavailable"
    snapshot = as_utc(coverage.tracking_state_at)
    baseline_at = as_utc(baseline.baseline_at) if baseline is not None else None
    if (
        snapshot > period_start
        and coverage.coverage_origin == "creation"
        and as_utc(coverage.tracking_started_at) < period_end
    ):
        result = replay_assignee(coverage, histories, period_end, baseline)
        return "reliable" if result["known"] else "partial"
    if period_start < snapshot <= period_end and baseline_at is not None and baseline_at <= period_start:
        if (
            coverage.legacy_assignment_timestamps_ambiguous
            or coverage.legacy_assignment_timeline_inconsistent
        ):
            return "partial"
        before_cut = replay_assignee(
            coverage, histories, snapshot - timedelta(microseconds=1), baseline
        )
        after_cut = replay_assignee(coverage, histories, period_end)
        if (
            before_cut["known"]
            and after_cut["known"]
            and before_cut["assignee_id"] == coverage.tracking_state_assignee_id
        ):
            return "reliable"
        return "partial"
    if period_start < snapshot:
        if baseline_at is None or baseline_at > period_start:
            return "unavailable" if snapshot > period_end else "partial"
        result = replay_assignee(coverage, histories, period_end, baseline)
    else:
        result = replay_assignee(coverage, histories, period_end, baseline)
    return "reliable" if result["known"] else "partial"


def _completion_is_valid(completion, history_by_id):
    source = history_by_id.get(completion.source_history_id)
    if (
        source is None
        or source.work_item_id != completion.work_item_id
        or source.new_value != completion.status
        or completion.status not in FINAL
    ):
        return False
    if source.field_name == "status":
        return source.old_value in NON_FINAL
    return source.field_name == "status_initialized" and source.old_value is None


def _coverage(values):
    if not values or all(value == "unavailable" for value in values):
        return "unavailable"
    if all(value == "reliable" for value in values):
        return "reliable"
    return "partial"


def _weekly_bounds(start: date, end: date):
    cursor = start
    while cursor < end:
        iso_monday = cursor - timedelta(days=cursor.weekday())
        next_monday = iso_monday + timedelta(days=7)
        yield cursor, min(next_monday, end)
        cursor = min(next_monday, end)


def _local_boundary(day: date) -> datetime:
    return datetime.combine(day, time.min, REPORT_TZ).astimezone(timezone.utc)


def calculate_quarterly_statistics(
    db: Session,
    *,
    user_id: int,
    year: int,
    quarter: int,
    scope: str,
    organization_id: int | None = None,
    project_id: int | None = None,
) -> dict:
    start, end = quarter_dates(year, quarter)
    start_utc = _local_boundary(start)
    end_utc = _local_boundary(end)
    now_utc = datetime.now(timezone.utc)
    period_complete = end_utc <= now_utc
    if start_utc > now_utc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se pueden consultar estadísticas de un trimestre futuro.",
        )
    current_quarter = not period_complete
    report_cut = (
        end_utc - timedelta(microseconds=1)
        if period_complete
        else now_utc
    )
    project_statement = (
        select(Project.id)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(
            ProjectMember.user_id == user_id,
            Project.deleted_at.is_(None),
            Project.archived_at.is_(None),
        )
    )
    if scope == "personal":
        project_statement = project_statement.where(Project.organization_id.is_(None))
    elif scope == "organization":
        org = db.get(Organization, organization_id)
        if org is None or org.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Organización no encontrada.")
        member = db.get(OrganizationMember, (organization_id, user_id))
        if member is None:
            raise HTTPException(status_code=403, detail="No perteneces a la organización.")
        project_statement = project_statement.where(Project.organization_id == organization_id)
    elif scope == "project":
        project_statement = project_statement.where(Project.id == project_id)
    if scope not in {"personal", "organization"}:
        # The all and project scopes require current organization membership
        # for organization projects. Organization scope has already checked
        # its selected organization directly above.
        project_statement = project_statement.outerjoin(
            Organization, Organization.id == Project.organization_id
        ).where(
            (Project.organization_id.is_(None))
            | (
                (Organization.deleted_at.is_(None))
                & select(OrganizationMember.user_id)
                .where(
                    OrganizationMember.organization_id == Project.organization_id,
                    OrganizationMember.user_id == user_id,
                )
                .exists()
            )
        )

    project_ids = list(db.scalars(project_statement.distinct()).all())
    if scope == "project" and not project_ids:
        raise HTTPException(status_code=403, detail="No tienes acceso al proyecto.")
    tasks = list(
        db.scalars(
            select(WorkItem).where(
                WorkItem.project_id.in_(project_ids) if project_ids else False,
                WorkItem.type == "task",
                WorkItem.deleted_at.is_(None),
            )
        ).all()
    )
    task_ids = [item.id for item in tasks]
    if not task_ids:
        return _empty_result(
            year, quarter, start, end, scope, organization_id, project_id,
            now_utc=now_utc,
        )

    coverages = {
        row.work_item_id: row
        for row in db.scalars(
            select(WorkItemCompletionCoverage).where(
                WorkItemCompletionCoverage.work_item_id.in_(task_ids)
            )
        ).all()
    }
    assignment_baselines = {
        row.work_item_id: row
        for row in db.scalars(
            select(WorkItemAssignmentBaseline).where(
                WorkItemAssignmentBaseline.work_item_id.in_(task_ids)
            )
        ).all()
    }
    histories = list(
        db.scalars(
            select(WorkItemHistory)
            .where(
                WorkItemHistory.work_item_id.in_(task_ids),
                WorkItemHistory.field_name.in_(
                    ("status", "status_initialized", "assignee_id")
                ),
            )
            .order_by(WorkItemHistory.work_item_id, WorkItemHistory.changed_at, WorkItemHistory.id)
        ).all()
    )
    history_by_task = defaultdict(list)
    history_by_id = {}
    for history in histories:
        history_by_task[history.work_item_id].append(history)
        history_by_id[history.id] = history
    completions = list(
        db.scalars(
            select(WorkItemCompletion)
            .where(WorkItemCompletion.work_item_id.in_(task_ids))
            .order_by(WorkItemCompletion.completed_at, WorkItemCompletion.id)
        ).all()
    )

    tasks_by_id = {task.id: task for task in tasks}
    considered_tasks = [task for task in tasks if as_utc(task.created_at) < end_utc]
    completion_rows = []
    assignment_coverage = []
    state_coverage = []
    completion_problem_task_ids = set()
    completion_history_ids = set()
    unconfirmed_completion_relevant = False
    for completion in completions:
        source_valid = _completion_is_valid(completion, history_by_id)
        if not completion.completed_at_is_utc:
            coverage = coverages.get(completion.work_item_id)
            if (
                coverage is not None
                and coverage.coverage_origin == "migration"
                and coverage.legacy_completion_imported_count > 0
                and as_utc(coverage.tracking_started_at) <= start_utc
            ):
                # These rows were imported by the legacy backfill and are
                # explicitly outside the UTC-confirmed tracking interval.
                continue
            completion_problem_task_ids.add(completion.work_item_id)
            unconfirmed_completion_relevant = True
            continue
        if not source_valid:
            completion_problem_task_ids.add(completion.work_item_id)
            continue
        source_event = history_by_id[completion.source_history_id]
        if as_utc(source_event.changed_at) != as_utc(completion.completed_at):
            completion_problem_task_ids.add(completion.work_item_id)
            continue
        completion_history_ids.add(completion.source_history_id)
        completed_local = local_instant(completion.completed_at)
        if not (start <= completed_local.date() < end) or as_utc(completion.completed_at) > report_cut:
            continue
        task = tasks_by_id.get(completion.work_item_id)
        if task is None or as_utc(task.created_at) >= end_utc:
            # A completion attributed to a task created after the reporting
            # period contradicts the task's creation timestamp. Keep the
            # metric incomplete instead of counting an impossible event.
            completion_problem_task_ids.add(completion.work_item_id)
            continue
        completion_rows.append(completion)

    # Completion coverage is independent of state and assignment coverage.
    completion_coverage = []
    for task in considered_tasks:
        coverage = coverages.get(task.id)
        if coverage is None:
            completion_coverage.append("unavailable")
            continue
        tracking_cut = as_utc(coverage.tracking_started_at)
        instrumented = tracking_cut <= start_utc or (
            coverage.coverage_origin == "creation"
            and as_utc(coverage.tracking_started_at) < end_utc
        )
        if instrumented:
            for event in history_by_task[task.id]:
                event_at = as_utc(event.changed_at)
                is_initial_final = (
                    event.field_name == "status_initialized"
                    and event.old_value is None
                    and event.new_value in FINAL
                    and coverage.coverage_origin == "creation"
                )
                is_transition_final = (
                    event.field_name == "status"
                    and event.old_value in NON_FINAL
                    and event.new_value in FINAL
                    and event_at > tracking_cut
                )
                event_is_in_period = (
                    start_utc <= event_at < end_utc and event_at <= report_cut
                )
                if (
                    (is_initial_final or is_transition_final)
                    and event_is_in_period
                    and event.id not in completion_history_ids
                ):
                    completion_problem_task_ids.add(task.id)
        if task.id in completion_problem_task_ids:
            completion_coverage.append("partial")
        else:
            completion_coverage.append("reliable" if instrumented else "partial")
    considered_task_ids = {task.id for task in considered_tasks}
    if completion_problem_task_ids - considered_task_ids:
        completion_coverage.append("partial")
    # A demonstrably empty task population is a reliable zero, while missing
    # coverage on a task that existed in the period remains unknown.
    completion_cov = (
        _coverage(completion_coverage)
        if considered_tasks or completion_problem_task_ids
        else "reliable"
    )
    due_coverage = ["reliable" if row.due_date_known else "partial" for row in completion_rows]
    if not completion_rows and completion_coverage:
        due_coverage.append(completion_cov)
    due_cov = _coverage(due_coverage)

    observed_completed = len(completion_rows)
    completed = observed_completed if completion_cov == "reliable" else None
    comparable = [
        row for row in completion_rows if row.due_date_known and row.due_date_at_completion is not None
    ]
    on_time = sum(
        local_instant(row.completed_at).date() <= row.due_date_at_completion
        for row in comparable
    )
    pct = (
        round(on_time * 100.0 / len(comparable), 2)
        if comparable and completion_cov == "reliable" else None
    )
    comparable_count = len(comparable) if completion_cov == "reliable" else None
    completed_assignee_known = (
        sum(row.assignee_known and row.assignee_id_at_completion is not None for row in completion_rows)
        if completion_cov == "reliable" else None
    )
    completed_unassigned = (
        sum(row.assignee_known and row.assignee_id_at_completion is None for row in completion_rows)
        if completion_cov == "reliable" else None
    )
    completed_unknown = (
        sum(not row.assignee_known for row in completion_rows)
        if completion_cov == "reliable" else None
    )

    end_cut = report_cut
    start_cut = start_utc - timedelta(microseconds=1)
    pending_end = 0
    pending_known = pending_unassigned = pending_unknown = 0
    carried_in = new_cycles = 0
    can_determine_end = True
    can_determine_load = True
    for task in tasks:
        # A task created on or after the exclusive quarter end did not belong
        # to this period. created_at is used only to establish existence.
        if as_utc(task.created_at) >= end_utc:
            continue
        coverage = coverages.get(task.id)
        events = history_by_task[task.id]
        if (
            coverage is not None
            and coverage.coverage_origin == "creation"
            and as_utc(coverage.tracking_started_at) > start_cut
        ):
            state_start = {"known": True, "active": False, "opened_at": None}
        elif (
            coverage is not None
            and coverage.coverage_origin == "migration"
            and as_utc(coverage.tracking_state_at) == start_utc
        ):
            # The cut itself is an observable state at the period boundary.
            state_start = replay_status(coverage, events, start_utc)
        else:
            state_start = replay_status(coverage, events, start_cut)
        state_end = replay_status(coverage, events, end_cut)
        if current_quarter and state_end["known"] and state_end["status"] != task.status:
            state_end = {"known": False, "active": None, "opened_at": None, "status": None}
        state_cov = _status_dimension(coverage, events, start_utc, end_cut)
        baseline = assignment_baselines.get(task.id)
        assign_cov = _assignment_dimension(
            coverage, events, start_utc, end_cut, baseline
        )
        if current_quarter:
            current_assignment = replay_assignee(coverage, events, end_cut, baseline)
            if current_assignment["known"] and current_assignment["assignee_id"] != task.assigned_to_id:
                assign_cov = "partial"
        state_coverage.append(state_cov)
        assignment_coverage.append(assign_cov)
        if not state_end["known"]:
            can_determine_end = False
            can_determine_load = False
            continue
        if not state_start["known"]:
            # We cannot prove whether the cycle was already open at quarter
            # start, even if it was later completed before the closing cut.
            can_determine_load = False
        elif state_start["active"]:
            carried_in += 1
        if state_end["active"]:
            pending_end += 1
            assignee = replay_assignee(coverage, events, end_cut, baseline)
            if current_quarter and assignee["known"] and assignee["assignee_id"] != task.assigned_to_id:
                assignee = {"known": False, "assignee_id": None}
            if assignee["known"]:
                if assignee["assignee_id"] is None:
                    pending_unassigned += 1
                else:
                    pending_known += 1
            else:
                pending_unknown += 1
    # Count starts within the quarter independently of whether those cycles
    # completed before quarter end.
    for task in tasks:
        if as_utc(task.created_at) >= end_utc:
            continue
        coverage = coverages.get(task.id)
        if coverage is None:
            continue
        events = history_by_task[task.id]
        if coverage.coverage_origin == "creation":
            created_at = as_utc(coverage.tracking_started_at)
            if start_utc <= created_at < end_utc and coverage.tracking_state_status in NON_FINAL:
                new_cycles += 1
            elif start_utc <= created_at < end_utc and coverage.tracking_state_status in FINAL:
                # Directly-created final tasks have a completion tied to the
                # initial status event; that event is a new statistical unit.
                new_cycles += sum(
                    1 for row in completion_rows
                    if row.work_item_id == task.id
                    and row.source_history_id in history_by_id
                    and history_by_id[row.source_history_id].field_name == "status_initialized"
                )
        for event in _status_events(events):
            event_at = as_utc(event.changed_at)
            if (
                coverage.tracking_state_at is not None
                and event_at > as_utc(coverage.tracking_state_at)
                and start_utc <= event_at < end_utc
                and event.old_value in FINAL
                and event.new_value in NON_FINAL
            ):
                new_cycles += 1
    pending_result = pending_end if can_determine_end else None
    if not can_determine_load:
        carried_result = None
        new_result = None
    else:
        carried_result = carried_in
        new_result = new_cycles if completion_cov == "reliable" else None
    if not can_determine_end:
        pending_known_result = pending_unassigned_result = pending_unknown_result = None
    else:
        pending_known_result = pending_known
        pending_unassigned_result = pending_unassigned
        pending_unknown_result = pending_unknown
    total_cycles = (
        observed_completed + pending_result
        if pending_result is not None and completion_cov == "reliable"
        else None
    )

    # Weekly points are emitted only where both the completion tally and the
    # pending-state cut can be established. Required pace is a derived linear
    # reference from actual progress at this cut to the period load at quarter end.
    weekly = []
    boundaries = list(_weekly_bounds(start, end))
    now_local = now_utc.astimezone(REPORT_TZ)
    for week_start, week_end in boundaries:
        cut_day = week_end
        planned_cut = _local_boundary(cut_day) - timedelta(microseconds=1)
        cut = min(planned_cut, report_cut)
        cumulative = sum(
            as_utc(row.completed_at) <= cut for row in completion_rows
        )
        weekly_pending = 0
        point_ok = True
        for task in tasks:
            if as_utc(task.created_at) >= cut:
                continue
            state = replay_status(coverages.get(task.id), history_by_task[task.id], cut)
            if not state["known"]:
                point_ok = False
                break
            weekly_pending += bool(state["active"])
        point_cov = (
            "reliable"
            if point_ok and completion_cov == "reliable"
            else "partial"
        )
        if not point_ok:
            weekly_pending_value = cumulative_value = required = required_per_week = None
            point_cov = "unavailable"
        else:
            weekly_pending_value = weekly_pending
            cumulative_value = cumulative
            known_load = total_cycles
            elapsed = max(0, (cut.astimezone(REPORT_TZ).date() - start).days)
            length = (end - start).days


            known_load = total_cycles
            elapsed = max(0, (cut.astimezone(REPORT_TZ).date() - start).days)
            length = (end - start).days

            if known_load is None or length <= 0:
                required = None
            else:
                required = round(known_load * min(elapsed / length, 1.0), 2)

            if period_complete and cut >= report_cut:
                required_per_week = (
                    0.0 if weekly_pending == 0 else None
                )
            else:
                remaining_weeks = max(
                    (end_utc - cut).total_seconds()
                    / (7.0 * 24.0 * 60.0 * 60.0),
                    0.0,
                )
                required_per_week = (
                    round(weekly_pending / remaining_weeks, 2)
                    if remaining_weeks > 0
                    else (0.0 if weekly_pending == 0 else None)
                )
        # For the current quarter, cuts beyond now would invent future progress.
        if current_quarter and planned_cut > now_utc and week_start > now_local.date():
            cumulative_value = weekly_pending_value = required = required_per_week = None
            point_cov = "unavailable"
        weekly.append({
            "week_start": week_start,
            "week_end": week_end,
            "completed_cumulative": cumulative_value,
            "pending_at_cut": weekly_pending_value,
            "required_cumulative": required,
            "required_per_week": required_per_week,
            "coverage": point_cov,
        })

    status_cov = _coverage(state_coverage) if considered_tasks else "reliable"
    assign_cov = _coverage(assignment_coverage) if considered_tasks else "reliable"
    warnings = []
    if current_quarter:
        warnings.append({"code": "quarter_in_progress", "message": "El periodo continúa abierto; las cifras se calculan hasta as_of y pueden cambiar con nuevas tareas o ciclos."})
    if any(coverages.get(task.id) is None for task in considered_tasks):
        warnings.append({"code": "coverage_snapshot_missing", "message": "Hay tareas sin snapshot de cobertura; sus ciclos pendientes no se consideran fiables."})
    if completion_cov != "reliable":
        warnings.append({"code": "completion_history_partial", "message": "Parte del historial de finalizaciones no tiene timestamp o evento de origen verificable."})
    if status_cov != "reliable":
        warnings.append({"code": "state_history_partial", "message": "El estado o los ciclos no pueden reconstruirse para todo el ámbito y periodo."})
    if assign_cov != "reliable":
        warnings.append({"code": "assignment_history_partial", "message": "La atribución de responsables es parcial; desconocido no equivale a sin asignar."})
    if due_cov != "reliable":
        warnings.append({"code": "due_date_snapshot_partial", "message": "Algunos vencimientos históricos no están confirmados."})
    if not comparable:
        warnings.append({"code": "no_comparable_completions", "message": "No hay finalizaciones con timestamp UTC y vencimiento no nulo confirmados para calcular puntualidad."})
    if unconfirmed_completion_relevant:
        warnings.append({"code": "unconfirmed_completion_timestamps", "message": "Hay finalizaciones históricas con zona horaria no confirmada; se excluyen de las métricas temporales exactas."})

    return {
        "year": year, "quarter": quarter, "timezone": "Europe/Madrid",
        "period_start": start, "period_end_exclusive": end,
        "as_of": report_cut if current_quarter else end_utc,
        "period_complete": not current_quarter,
        "scope": scope, "organization_id": organization_id, "project_id": project_id,
        "total_cycles": total_cycles, "completed_cycles": completed,
        "pending_at_close": pending_result,
        "completed_on_time_percent": pct,
        "punctuality_comparable_count": comparable_count,
        "completed_with_known_assignee": completed_assignee_known,
        "completed_unassigned": completed_unassigned,
        "completed_assignee_unknown": completed_unknown,
        "pending_with_known_assignee": pending_known_result,
        "pending_unassigned": pending_unassigned_result,
        "pending_assignee_unknown": pending_unknown_result,
        "load": {"carried_in": carried_result, "new_cycles": new_result},
        "coverage": {"state_and_cycles": status_cov, "assignments": assign_cov, "completions": completion_cov, "due_date_snapshots": due_cov},
        "warnings": warnings,
        "weekly": weekly,
    }


def _empty_result(
    year, quarter, start, end, scope, organization_id, project_id,
    *, now_utc: datetime | None = None,
):
    now = now_utc or datetime.now(timezone.utc)
    now_local = now.astimezone(REPORT_TZ)
    end_at = _local_boundary(end)
    is_current = end_at > now
    weekly = []
    for week_start, week_end in _weekly_bounds(start, end):
        future = is_current and week_start > now_local.date()
        value = None if future else 0
        weekly.append({
            "week_start": week_start,
            "week_end": week_end,
            "completed_cumulative": value,
            "pending_at_cut": value,
            "required_cumulative": value,
            "required_per_week": value,
            "coverage": "unavailable" if future else "reliable",
        })
    return {
        "year": year, "quarter": quarter, "timezone": "Europe/Madrid",
        "period_start": start, "period_end_exclusive": end,
        "as_of": now if is_current else end_at,
        "period_complete": not is_current,
        "scope": scope, "organization_id": organization_id, "project_id": project_id,
        "total_cycles": 0, "completed_cycles": 0, "pending_at_close": 0,
        "completed_on_time_percent": None, "punctuality_comparable_count": 0,
        "completed_with_known_assignee": 0, "completed_unassigned": 0,
        "completed_assignee_unknown": 0, "pending_with_known_assignee": 0,
        "pending_unassigned": 0, "pending_assignee_unknown": 0,
        "load": {"carried_in": 0, "new_cycles": 0},
        "coverage": {"state_and_cycles": "reliable", "assignments": "reliable", "completions": "reliable", "due_date_snapshots": "reliable"},
        "warnings": ([{"code": "quarter_in_progress", "message": "El periodo continúa abierto; las cifras se calculan hasta as_of y pueden cambiar con nuevas tareas o ciclos."}] if is_current else []),
        "weekly": weekly,
    }
