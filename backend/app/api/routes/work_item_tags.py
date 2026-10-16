
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.project_access import require_project_organization_membership
from app.db.session import get_db
from app.models.user import User
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.work_item import WorkItem
from app.models.tag import Tag
from app.models.work_item_tag import WorkItemTag
from app.schemas.work_item_tag import (
    WorkItemTagCreate,
    WorkItemTagResponse,
)

router = APIRouter(
    prefix="/work-items/{work_item_id}/tags",
    tags=["Work item tags"],
)


def get_accessible_item(
    db: Session,
    work_item_id: int,
    user: User,
) -> WorkItem:
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

    return item


@router.get("/", response_model=list[WorkItemTagResponse])
def list_work_item_tags(
    work_item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = get_accessible_item(db, work_item_id, user)

    rows = db.execute(
        select(Tag.id, Tag.name, Tag.color)
        .join(WorkItemTag, WorkItemTag.tag_id == Tag.id)
        .where(WorkItemTag.work_item_id == item.id)
        .order_by(Tag.name.asc())
    ).all()

    return [
        WorkItemTagResponse(id=row.id, name=row.name, color=row.color)
        for row in rows
    ]


@router.post("/", status_code=status.HTTP_201_CREATED)
def add_tag_to_work_item(
    work_item_id: int,
    data: WorkItemTagCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = get_accessible_item(db, work_item_id, user)
    tag = db.get(Tag, data.tag_id)

    if tag is None or tag.project_id != item.project_id:
        raise HTTPException(
            status_code=404,
            detail="Etiqueta no encontrada en este proyecto.",
        )

    association = db.get(WorkItemTag, (item.id, tag.id))

    if association is not None:
        raise HTTPException(
            status_code=409,
            detail="La etiqueta ya está asociada a esta tarea.",
        )

    try:
        db.add(
            WorkItemTag(
                work_item_id=item.id,
                tag_id=tag.id,
                added_by_id=user.id,
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La etiqueta ya está asociada a esta tarea.",
        ) from exc
    except Exception:
        db.rollback()
        raise

    return {"message": "Etiqueta asociada correctamente."}


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_tag_from_work_item(
    work_item_id: int,
    tag_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = get_accessible_item(db, work_item_id, user)
    association = db.get(WorkItemTag, (item.id, tag_id))

    if association is None:
        raise HTTPException(
            status_code=404,
            detail="La etiqueta no está asociada a esta tarea.",
        )

    try:
        db.delete(association)
        db.commit()
    except Exception:
        db.rollback()
        raise
