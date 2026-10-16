
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.project_access import require_project_organization_membership
from app.db.session import get_db
from app.models.user import User
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.work_item import WorkItem
from app.models.work_item_history import WorkItemHistory
from app.schemas.work_item_history import WorkItemHistoryResponse

router = APIRouter(
    prefix="/work-items/{work_item_id}/history",
    tags=["Work item history"],
)


@router.get("/", response_model=list[WorkItemHistoryResponse])
def list_work_item_history(
    work_item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = db.get(WorkItem, work_item_id)

    if item is None:
        raise HTTPException(status_code=404, detail="Tarea no encontrada.")

    project = db.get(Project, item.project_id)

    if project is None or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado.")

    require_project_organization_membership(
        db,
        project,
        user.id,
        detail="No tienes acceso a este proyecto.",
    )

    membership = db.get(ProjectMember, (project.id, user.id))

    if membership is None:
        raise HTTPException(
            status_code=403,
            detail="No tienes acceso a este proyecto.",
        )

    return db.scalars(
        select(WorkItemHistory)
        .where(WorkItemHistory.work_item_id == item.id)
        .order_by(WorkItemHistory.changed_at.desc())
    ).all()
