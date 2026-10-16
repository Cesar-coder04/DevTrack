
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.project_access import require_project_organization_membership
from app.db.session import get_db
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.models.work_item import WorkItem
from app.models.work_item_history import WorkItemHistory
from app.schemas.work_item import (
    WorkItemCreate,
    WorkItemResponse,
    WorkItemStatus,
    WorkItemUpdate,
)

router = APIRouter(
    prefix="/projects/{project_id}/work-items",
    tags=["Work Items"],
)


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
        allow_unorganized=False,
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
        db.add(item)
        db.flush()

        history = WorkItemHistory(
            work_item_id=item.id,
            changed_by_id=current_user.id,
            field_name="created",
            old_value=None,
            new_value=item.title,
        )
        db.add(history)
        db.commit()
        db.refresh(item)
    except Exception:
        db.rollback()
        raise

    return item


@router.get("/", response_model=list[WorkItemResponse])
def list_work_items(
    project_id: int,
    status_filter: WorkItemStatus | None = None,
    priority_filter: str | None = None,
    assignee_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_project_access(project_id, current_user, db)

    statement = select(WorkItem).where(WorkItem.project_id == project_id)

    if status_filter:
        statement = statement.where(WorkItem.status == status_filter)

    if priority_filter:
        statement = statement.where(WorkItem.priority == priority_filter)

    if assignee_id is not None:
        statement = statement.where(WorkItem.assigned_to_id == assignee_id)

    statement = statement.order_by(WorkItem.created_at.desc())

    return list(db.scalars(statement).all())


@router.get("/{work_item_id}", response_model=WorkItemResponse)
def get_work_item(
    project_id: int,
    work_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_project_access(project_id, current_user, db)

    item = db.get(WorkItem, work_item_id)

    if item is None or item.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tarea no encontrada.",
        )

    return item


@router.patch("/{work_item_id}", response_model=WorkItemResponse)
def update_work_item(
    project_id: int,
    work_item_id: int,
    item_data: WorkItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project, _ = get_project_access(project_id, current_user, db)

    item = db.get(WorkItem, work_item_id)

    if item is None or item.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tarea no encontrada.",
        )

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
                )
                db.add(history)
                setattr(item, model_field, new_value)

        item.updated_at = datetime.now(timezone.utc)

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

    try:
        db.delete(item)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return None
