from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.models.work_item import WorkItem
from app.schemas.work_item import WorkItemPriority, WorkItemStatus
from app.schemas.user_work_item import UserIssueResponse, UserWorkItemResponse


router = APIRouter(
    prefix="/users/me",
    tags=["User work items"],
)


def parse_optional_date(value: str | None, parameter_name: str) -> date | None:
    if value is None or not value.strip():
        return None

    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{parameter_name} debe tener formato YYYY-MM-DD.",
        ) from None


@router.get("/work-items/", response_model=list[UserWorkItemResponse])
def list_my_work_items(
    status_filter: WorkItemStatus | None = None,
    priority_filter: WorkItemPriority | None = None,
    project_id: int | None = None,
    organization_id: int | None = None,
    due_date_from: str | None = None,
    due_date_to: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    start_date = parse_optional_date(due_date_from, "due_date_from")
    end_date = parse_optional_date(due_date_to, "due_date_to")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="due_date_from no puede ser posterior a due_date_to.",
        )

    project_membership = ProjectMember
    organization_membership = OrganizationMember
    statement = (
        select(
            WorkItem,
            Project.name,
            Project.organization_id,
            Organization.name,
        )
        .join(Project, Project.id == WorkItem.project_id)
        .outerjoin(Organization, Organization.id == Project.organization_id)
        .join(
            project_membership,
            and_(
                project_membership.project_id == Project.id,
                project_membership.user_id == current_user.id,
            ),
        )
        .outerjoin(
            organization_membership,
            and_(
                organization_membership.organization_id
                == Project.organization_id,
                organization_membership.user_id == current_user.id,
            ),
        )
        .where(
            WorkItem.assigned_to_id == current_user.id,
            WorkItem.type == "task",
            WorkItem.deleted_at.is_(None),
            Project.deleted_at.is_(None),
            Project.archived_at.is_(None),
            or_(
                Project.organization_id.is_(None),
                and_(
                    Organization.id.is_not(None),
                    Organization.deleted_at.is_(None),
                    organization_membership.user_id.is_not(None),
                ),
            ),
        )
    )

    if status_filter is not None:
        statement = statement.where(WorkItem.status == status_filter)
    if priority_filter is not None:
        statement = statement.where(WorkItem.priority == priority_filter)
    if project_id is not None:
        statement = statement.where(Project.id == project_id)
    if organization_id is not None:
        statement = statement.where(Project.organization_id == organization_id)
    if start_date is not None:
        statement = statement.where(WorkItem.due_date >= start_date)
    if end_date is not None:
        # Exclusive next-day bound includes every time on due_date_to if the
        # database column is ever represented as a datetime.
        statement = statement.where(
            WorkItem.due_date < end_date + timedelta(days=1)
        )

    today = datetime.now(timezone.utc).date()
    is_overdue = and_(
        WorkItem.due_date < today,
        WorkItem.status.not_in(("resolved", "closed")),
    )
    due_date_group = case(
        (is_overdue, 0),
        (WorkItem.due_date.is_not(None), 1),
        else_=2,
    )
    overdue_due_date = case(
        (is_overdue, WorkItem.due_date),
        else_=None,
    )
    upcoming_due_date = case(
        (
            and_(~is_overdue, WorkItem.due_date.is_not(None)),
            WorkItem.due_date,
        ),
        else_=None,
    )
    statement = statement.order_by(
        due_date_group,
        overdue_due_date.desc(),
        upcoming_due_date.asc(),
        WorkItem.created_at.desc(),
    )

    rows = db.execute(statement).all()
    return [
        UserWorkItemResponse(
            id=item.id,
            type=item.type,
            title=item.title,
            status=item.status,
            priority=item.priority,
            project_id=item.project_id,
            project_name=project_name,
            organization_id=organization_id_value,
            organization_name=organization_name,
            due_date=item.due_date,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for (
            item,
            project_name,
            organization_id_value,
            organization_name,
        ) in rows
    ]


@router.get("/issues/", response_model=list[UserIssueResponse])
def list_my_issues(
    status_filter: WorkItemStatus | None = None,
    assignee_id: int | None = Query(default=None, gt=0),
    unassigned: bool = False,
    priority_filter: WorkItemPriority | None = None,
    sort_by: Literal["priority", "created_at", "updated_at"] = "priority",
    sort_order: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if unassigned and assignee_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="assignee_id y unassigned no se pueden combinar.",
        )

    organization_membership = OrganizationMember
    statement = (
        select(
            WorkItem,
            User.display_name,
            Project.name,
            Project.organization_id,
            Organization.name,
        )
        .join(Project, Project.id == WorkItem.project_id)
        .outerjoin(User, User.id == WorkItem.assigned_to_id)
        .outerjoin(Organization, Organization.id == Project.organization_id)
        .join(
            ProjectMember,
            and_(
                ProjectMember.project_id == Project.id,
                ProjectMember.user_id == current_user.id,
            ),
        )
        .outerjoin(
            organization_membership,
            and_(
                organization_membership.organization_id
                == Project.organization_id,
                organization_membership.user_id == current_user.id,
            ),
        )
        .where(
            WorkItem.type == "issue",
            WorkItem.deleted_at.is_(None),
            Project.deleted_at.is_(None),
            Project.archived_at.is_(None),
            or_(
                Project.organization_id.is_(None),
                and_(
                    Organization.id.is_not(None),
                    Organization.deleted_at.is_(None),
                    organization_membership.user_id.is_not(None),
                ),
            ),
        )
    )

    if status_filter is not None:
        statement = statement.where(WorkItem.status == status_filter)
    if assignee_id is not None:
        statement = statement.where(WorkItem.assigned_to_id == assignee_id)
    elif unassigned:
        statement = statement.where(WorkItem.assigned_to_id.is_(None))
    if priority_filter is not None:
        statement = statement.where(WorkItem.priority == priority_filter)

    if sort_by == "priority":
        priority_rank = case(
            (WorkItem.priority == "low", 1),
            (WorkItem.priority == "medium", 2),
            (WorkItem.priority == "high", 3),
            (WorkItem.priority == "urgent", 4),
            else_=0,
        )
        primary_sort = (
            priority_rank.asc()
            if sort_order == "asc"
            else priority_rank.desc()
        )
    elif sort_by == "created_at":
        primary_sort = (
            WorkItem.created_at.asc()
            if sort_order == "asc"
            else WorkItem.created_at.desc()
        )
    else:
        primary_sort = (
            WorkItem.updated_at.asc()
            if sort_order == "asc"
            else WorkItem.updated_at.desc()
        )

    statement = statement.order_by(primary_sort, WorkItem.id.asc())
    rows = db.execute(statement).all()

    return [
        UserIssueResponse(
            id=item.id,
            type=item.type,
            title=item.title,
            description=item.description,
            status=item.status,
            priority=item.priority,
            assignee_id=item.assigned_to_id,
            assignee_display_name=assignee_display_name,
            project_id=item.project_id,
            project_name=project_name,
            organization_id=organization_id_value,
            organization_name=organization_name,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for (
            item,
            assignee_display_name,
            project_name,
            organization_id_value,
            organization_name,
        ) in rows
    ]
