
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.project_access import require_project_organization_membership
from app.api.work_item_access import ensure_work_item_active
from app.db.session import get_db
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.organization import Organization
from app.models.user import User
from app.models.work_item import WorkItem
from app.models.work_item_assignment_baseline import WorkItemAssignmentBaseline
from app.models.work_item_completion import WorkItemCompletion
from app.models.work_item_completion_coverage import WorkItemCompletionCoverage
from app.models.work_item_history import WorkItemHistory
from app.schemas.work_item import (
    WorkItemCreate,
    WorkItemDetailResponse,
    WorkItemListResponse,
    WorkItemResponse,
    WorkItemStatus,
    WorkItemType,
    WorkItemUpdate,
)

router = APIRouter(
    prefix="/projects/{project_id}/work-items",
    tags=["Work Items"],
)

FINAL_STATUSES = frozenset(("resolved", "closed"))


def get_project_access(
    project_id: int,
    current_user: User,
    db: Session,
):
    project = db.get(Project, project_id)

    if (
        project is None
        or project.deleted_at is not None
        or project.archived_at is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proyecto no encontrado o archivado.",
        )

    require_project_organization_membership(
        db,
        project,
        current_user.id,
        detail="No perteneces a la organización.",
    )

    project_membership = db.get(
        ProjectMember,
        (project_id, current_user.id),
    )

    if project_membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No perteneces a este proyecto.",
        )

    return project, project_membership


def check_assignee(
    project_id: int,
    assignee_id: int | None,
    project: Project,
    db: Session,
):
    if assignee_id is None:
        return

    assignee = db.get(User, assignee_id)

    if assignee is None or not assignee.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El usuario asignado no existe o está inactivo.",
        )

    project_membership = db.get(ProjectMember, (project_id, assignee_id))

    if project_membership is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La persona asignada debe pertenecer al proyecto.",
        )


def _assignment_value(value: int | None) -> str | None:
    return str(value) if value is not None else None


def _record_assignment_coverage(
    db: Session,
    item: WorkItem,
    old_assignee_id: int | None,
    event_at: datetime,
) -> None:
    """Record assignment continuity metadata in the task transaction."""
    with db.no_autoflush:
        coverage = db.get(WorkItemCompletionCoverage, item.id)
    if not isinstance(coverage, WorkItemCompletionCoverage):
        coverage = None
    if coverage is None:
        # Defensive recovery for rows created outside the current API. We can
        # establish a known point now, but cannot claim earlier continuity.
        coverage = WorkItemCompletionCoverage(
            work_item_id=item.id,
            tracking_started_at=event_at,
            tracking_state_at=event_at,
            tracking_state_status=item.status,
            tracking_state_assignee_id=old_assignee_id,
            tracking_state_assignee_known=True,
            tracking_open_cycle_started_at=None,
            coverage_origin="migration",
            captured_since_creation=False,
            legacy_status_event_count=0,
            legacy_completion_candidate_count=0,
            legacy_completion_imported_count=0,
            legacy_completion_omitted_count=0,
            legacy_status_timestamps_ambiguous=False,
            legacy_status_timeline_inconsistent=False,
            legacy_assignment_history_partial=True,
            legacy_assignment_timestamps_ambiguous=False,
            legacy_assignment_timeline_inconsistent=False,
            assignment_event_count=0,
            assignment_sequence_reconstructible=False,
            assignment_timestamps_ambiguous=True,
            assignment_timeline_inconsistent=False,
        )
        db.add(coverage)
        with db.no_autoflush:
            assignment_baseline = db.get(WorkItemAssignmentBaseline, item.id)
        if not isinstance(assignment_baseline, WorkItemAssignmentBaseline):
            db.add(
                WorkItemAssignmentBaseline(
                    work_item_id=item.id,
                    assignee_id=old_assignee_id,
                    baseline_at=event_at,
                    baseline_kind="migration",
                )
            )

    with db.no_autoflush:
        latest_event = db.scalar(
            select(WorkItemHistory)
            .where(
                WorkItemHistory.work_item_id == item.id,
                WorkItemHistory.field_name == "assignee_id",
                WorkItemHistory.changed_at >= coverage.tracking_state_at,
            )
            .order_by(
                WorkItemHistory.changed_at.desc(), WorkItemHistory.id.desc()
            )
            .limit(1)
        )
    if not isinstance(latest_event, WorkItemHistory):
        latest_event = None
    expected_old_value = (
        latest_event.new_value
        if latest_event is not None
        else _assignment_value(coverage.tracking_state_assignee_id)
    )
    if (
        not coverage.tracking_state_assignee_known
        or expected_old_value != _assignment_value(old_assignee_id)
    ):
        coverage.assignment_timeline_inconsistent = True
        coverage.assignment_sequence_reconstructible = False

    if latest_event is not None:
        # MySQL DATETIME columns in this project do not retain fractional
        # seconds. Treat equal stored seconds conservatively as ambiguous.
        prior_at = latest_event.changed_at.replace(tzinfo=timezone.utc)
        event_at_utc = (
            event_at.replace(tzinfo=timezone.utc)
            if event_at.tzinfo is None
            else event_at.astimezone(timezone.utc)
        )
        if prior_at.replace(microsecond=0) == event_at_utc.replace(microsecond=0):
            coverage.assignment_timestamps_ambiguous = True
            coverage.assignment_sequence_reconstructible = False

    coverage.assignment_event_count += 1


@router.post(
    "/",
    response_model=WorkItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_work_item(
    project_id: int,
    item_data: WorkItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project, _ = get_project_access(project_id, current_user, db)
    check_assignee(project_id, item_data.assignee_id, project, db)

    item = WorkItem(
        project_id=project_id,
        type="task",
        title=item_data.title,
        description=item_data.description,
        status=item_data.status,
        priority=item_data.priority,
        created_by_id=current_user.id,
        assigned_to_id=item_data.assignee_id,
        due_date=(
            item_data.due_date.date()
            if item_data.due_date is not None
            else None
        ),
    )

    try:
        event_at = datetime.now(timezone.utc)
        db.add(item)
        db.flush()
        db.add(
            WorkItemAssignmentBaseline(
                work_item_id=item.id,
                assignee_id=item.assigned_to_id,
                baseline_at=event_at,
                baseline_kind="creation",
            )
        )
        db.add(
            WorkItemCompletionCoverage(
                work_item_id=item.id,
                tracking_started_at=event_at,
                tracking_state_at=event_at,
                tracking_state_status=item.status,
                tracking_state_assignee_id=item.assigned_to_id,
                tracking_state_assignee_known=True,
                tracking_open_cycle_started_at=(
                    event_at if item.status not in FINAL_STATUSES else None
                ),
                coverage_origin="creation",
                captured_since_creation=True,
                legacy_status_event_count=0,
                legacy_completion_candidate_count=0,
                legacy_completion_imported_count=0,
                legacy_completion_omitted_count=0,
                legacy_status_timestamps_ambiguous=False,
                legacy_status_timeline_inconsistent=False,
                legacy_assignment_history_partial=False,
                legacy_assignment_timestamps_ambiguous=False,
                legacy_assignment_timeline_inconsistent=False,
                assignment_event_count=0,
                assignment_sequence_reconstructible=True,
                assignment_timestamps_ambiguous=False,
                assignment_timeline_inconsistent=False,
            )
        )

        history = WorkItemHistory(
            work_item_id=item.id,
            changed_by_id=current_user.id,
            field_name="created",
            old_value=None,
            new_value=item.title,
            changed_at=event_at,
        )
        initial_status = WorkItemHistory(
            work_item_id=item.id,
            changed_by_id=current_user.id,
            field_name="status_initialized",
            old_value=None,
            new_value=item.status,
            changed_at=event_at,
        )
        initial_due_date = WorkItemHistory(
            work_item_id=item.id,
            changed_by_id=current_user.id,
            field_name="due_date_initialized",
            old_value=None,
            new_value=(str(item.due_date) if item.due_date is not None else None),
            changed_at=event_at,
        )
        for entry in (history, initial_status, initial_due_date):
            db.add(entry)
        db.flush()

        if item.status in FINAL_STATUSES:
            db.add(
                WorkItemCompletion(
                    work_item_id=item.id,
                    source_history_id=initial_status.id,
                    project_id_at_completion=item.project_id,
                    assignee_id_at_completion=item.assigned_to_id,
                    completed_at=event_at,
                    completed_at_is_utc=True,
                    status=item.status,
                    due_date_at_completion=item.due_date,
                    due_date_known=True,
                    assignee_known=True,
                )
            )
        db.commit()
        db.refresh(item)
    except Exception:
        db.rollback()
        raise

    return item


@router.get("/", response_model=list[WorkItemListResponse])
def list_work_items(
    project_id: int,
    status_filter: WorkItemStatus | None = None,
    priority_filter: str | None = None,
    assignee_id: int | None = None,
    type_filter: WorkItemType | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_project_access(project_id, current_user, db)

    statement = (
        select(WorkItem, User.display_name)
        .outerjoin(User, WorkItem.assigned_to_id == User.id)
        .where(WorkItem.project_id == project_id)
        .where(WorkItem.deleted_at.is_(None))
    )

    if status_filter:
        statement = statement.where(WorkItem.status == status_filter)

    if priority_filter:
        statement = statement.where(WorkItem.priority == priority_filter)

    if assignee_id is not None:
        statement = statement.where(WorkItem.assigned_to_id == assignee_id)

    if type_filter is not None:
        statement = statement.where(WorkItem.type == type_filter)

    statement = statement.order_by(WorkItem.created_at.desc())

    rows = db.execute(statement).all()
    return [
        WorkItemListResponse.model_validate(item).model_copy(
            update={"assignee_display_name": assignee_display_name}
        )
        for item, assignee_display_name in rows
    ]


@router.get("/{work_item_id}", response_model=WorkItemDetailResponse)
def get_work_item(
    project_id: int,
    work_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_project_access(project_id, current_user, db)

    row = db.execute(
        select(
            WorkItem,
            User.display_name,
            Project.name,
            Project.organization_id,
            Organization.name,
        )
        .join(Project, WorkItem.project_id == Project.id)
        .outerjoin(Organization, Project.organization_id == Organization.id)
        .outerjoin(User, WorkItem.assigned_to_id == User.id)
        .where(WorkItem.id == work_item_id, WorkItem.project_id == project_id)
    ).one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tarea no encontrada.",
        )

    item, assignee_display_name, project_name, organization_id, organization_name = row
    ensure_work_item_active(item)

    response_data = WorkItemResponse.model_validate(item).model_dump()
    response_data["created_by_id"] = item.created_by_id
    response_data["assigned_to_id"] = item.assigned_to_id
    response_data.update(
        {
            "project_name": project_name,
            "organization_id": organization_id,
            "organization_name": organization_name,
            "assignee_display_name": assignee_display_name,
        }
    )
    return WorkItemDetailResponse.model_validate(response_data)


@router.patch("/{work_item_id}", response_model=WorkItemResponse)
def update_work_item(
    project_id: int,
    work_item_id: int,
    item_data: WorkItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project, _ = get_project_access(project_id, current_user, db)

    # MySQL applies SELECT ... FOR UPDATE here; SQLite ignores row locks, so
    # this clause is a production concurrency guard, not a test-only mutex.
    item = db.get(
        WorkItem,
        work_item_id,
        with_for_update=True,
        populate_existing=True,
    )

    if item is None or item.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tarea no encontrada.",
        )

    ensure_work_item_active(item)

    changes = item_data.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes indicar al menos un campo.",
        )

    check_assignee(
        project_id,
        changes.get("assignee_id", item.assigned_to_id),
        project,
        db,
    )

    try:
        event_at = datetime.now(timezone.utc)
        old_status = item.status
        old_assignee_id = item.assigned_to_id
        new_status = changes.get("status", old_status)
        updated_assignee_id = changes.get("assignee_id", item.assigned_to_id)
        updated_due_date = changes.get("due_date", item.due_date)
        if updated_due_date is not None and hasattr(updated_due_date, "date"):
            updated_due_date = updated_due_date.date()

        status_history = None
        for field, new_value in changes.items():
            model_field = (
                "assigned_to_id" if field == "assignee_id" else field
            )
            old_value = getattr(item, model_field)
            if field == "due_date" and new_value is not None:
                new_value = new_value.date()

            if old_value != new_value:
                history = WorkItemHistory(
                    work_item_id=item.id,
                    changed_by_id=current_user.id,
                    field_name=field,
                    old_value=str(old_value) if old_value is not None else None,
                    new_value=str(new_value) if new_value is not None else None,
                    changed_at=event_at,
                )
                db.add(history)
                if field == "status":
                    status_history = history
                setattr(item, model_field, new_value)

        if (
            item.type == "task"
            and "assignee_id" in changes
            and old_assignee_id != updated_assignee_id
        ):
            _record_assignment_coverage(
                db,
                item,
                old_assignee_id,
                event_at,
            )

        item.updated_at = event_at

        if (
            item.type == "task"
            and old_status not in FINAL_STATUSES
            and new_status in FINAL_STATUSES
            and status_history is not None
        ):
            db.flush()
            db.add(
                WorkItemCompletion(
                    work_item_id=item.id,
                    source_history_id=status_history.id,
                    project_id_at_completion=item.project_id,
                    assignee_id_at_completion=updated_assignee_id,
                    completed_at=event_at,
                    completed_at_is_utc=True,
                    status=new_status,
                    due_date_at_completion=updated_due_date,
                    due_date_known=True,
                    assignee_known=True,
                )
            )

        db.commit()
        db.refresh(item)
    except Exception:
        db.rollback()
        raise

    return item


@router.delete("/{work_item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_work_item(
    project_id: int,
    work_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, membership = get_project_access(project_id, current_user, db)

    if membership.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los propietarios y administradores pueden eliminar tareas.",
        )

    item = db.get(WorkItem, work_item_id)

    if item is None or item.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tarea no encontrada.",
        )

    ensure_work_item_active(item)

    try:
        deleted_at = datetime.now(timezone.utc)
        result = db.execute(
            update(WorkItem.__table__)
            .where(
                WorkItem.id == item.id,
                WorkItem.deleted_at.is_(None),
            )
            .values(deleted_at=deleted_at)
        )
        if result.rowcount != 1:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tarea no encontrada.",
            )

        db.expire(item, ["deleted_at"])
        db.add(
            WorkItemHistory(
                work_item_id=item.id,
                changed_by_id=current_user.id,
                field_name="deleted",
                old_value=None,
                new_value=deleted_at.isoformat(),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return None
