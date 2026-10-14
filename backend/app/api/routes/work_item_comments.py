
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.work_item import WorkItem
from app.models.work_item_comment import WorkItemComment
from app.schemas.work_item_comment import (
    WorkItemCommentCreate,
    WorkItemCommentUpdate,
    WorkItemCommentResponse,
)

router = APIRouter(
    prefix="/work-items/{work_item_id}/comments",
    tags=["Work item comments"],
)


def get_accessible_work_item(
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

    membership = db.get(ProjectMember, (project.id, user.id))

    if membership is None:
        raise HTTPException(
            status_code=403,
            detail="No tienes acceso a este proyecto.",
        )

    return item


@router.post(
    "/",
    response_model=WorkItemCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    work_item_id: int,
    data: WorkItemCommentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = get_accessible_work_item(db, work_item_id, user)

    comment = WorkItemComment(
        work_item_id=item.id,
        user_id=user.id,
        content=data.content,
    )

    try:
        db.add(comment)
        db.commit()
        db.refresh(comment)
    except Exception:
        db.rollback()
        raise

    return comment


@router.get("/", response_model=list[WorkItemCommentResponse])
def list_comments(
    work_item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = get_accessible_work_item(db, work_item_id, user)

    return db.scalars(
        select(WorkItemComment)
        .where(WorkItemComment.work_item_id == item.id)
        .order_by(WorkItemComment.created_at.asc())
    ).all()


@router.patch("/{comment_id}", response_model=WorkItemCommentResponse)
def update_comment(
    work_item_id: int,
    comment_id: int,
    data: WorkItemCommentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = get_accessible_work_item(db, work_item_id, user)
    comment = db.get(WorkItemComment, comment_id)

    if comment is None or comment.work_item_id != item.id:
        raise HTTPException(status_code=404, detail="Comentario no encontrado.")

    if comment.user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Solo puedes editar tus propios comentarios.",
        )

    comment.content = data.content
    try:
        db.commit()
        db.refresh(comment)
    except Exception:
        db.rollback()
        raise

    return comment


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    work_item_id: int,
    comment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = get_accessible_work_item(db, work_item_id, user)
    comment = db.get(WorkItemComment, comment_id)

    if comment is None or comment.work_item_id != item.id:
        raise HTTPException(status_code=404, detail="Comentario no encontrado.")

    if comment.user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Solo puedes borrar tus propios comentarios.",
        )

    try:
        db.delete(comment)
        db.commit()
    except Exception:
        db.rollback()
        raise
