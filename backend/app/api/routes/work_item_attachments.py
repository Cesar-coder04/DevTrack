
from pathlib import Path
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.project_access import require_project_organization_membership
from app.db.session import get_db
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.work_item import WorkItem
from app.models.work_item_attachment import WorkItemAttachment
from app.models.user import User
from app.schemas.work_item_attachment import WorkItemAttachmentResponse


router = APIRouter(
    prefix="/work-items/{work_item_id}/attachments",
    tags=["Work item attachments"],
)

UPLOAD_DIR = Path(__file__).resolve().parents[3] / "uploads"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def get_accessible_work_item(
    db: Session,
    work_item_id: int,
    user_id: int,
) -> WorkItem:
    item = db.get(WorkItem, work_item_id)

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tarea no encontrada.",
        )

    project = db.get(Project, item.project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proyecto no encontrado.",
        )

    require_project_organization_membership(
        db,
        project,
        user_id,
        detail="No tienes acceso a esta tarea.",
    )

    membership = db.get(
        ProjectMember,
        (project.id, user_id),
    )

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a esta tarea.",
        )

    return item


@router.get("/", response_model=list[WorkItemAttachmentResponse])
def list_attachments(
    work_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_accessible_work_item(db, work_item_id, current_user.id)

    query = (
        select(WorkItemAttachment)
        .where(WorkItemAttachment.work_item_id == work_item_id)
        .order_by(WorkItemAttachment.uploaded_at.desc())
    )

    return db.scalars(query).all()


@router.post(
    "/",
    response_model=WorkItemAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    work_item_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_accessible_work_item(db, work_item_id, current_user.id)

    original_name = Path(file.filename or "archivo").name
    storage_key = f"{uuid4().hex}_{original_name}"
    content_type = file.content_type

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_DIR / storage_key
    size = 0

    try:
        try:
            with destination.open("wb") as output:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)

                    if size > MAX_FILE_SIZE:
                        raise HTTPException(
                            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                            detail="El archivo no puede superar los 10 MB.",
                        )

                    output.write(chunk)

            attachment = WorkItemAttachment(
                work_item_id=work_item_id,
                uploaded_by_id=current_user.id,
                filename=original_name,
                storage_key=storage_key,
                content_type=content_type,
                size_bytes=size,
            )

            db.add(attachment)
            db.commit()
        except Exception:
            db.rollback()
            destination.unlink(missing_ok=True)
            raise

        db.refresh(attachment)

        return attachment

    finally:
        await file.close()


@router.get("/{attachment_id}/download")
def download_attachment(
    work_item_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from fastapi.responses import FileResponse

    get_accessible_work_item(db, work_item_id, current_user.id)

    attachment = db.scalar(
        select(WorkItemAttachment).where(
            WorkItemAttachment.id == attachment_id,
            WorkItemAttachment.work_item_id == work_item_id,
        )
    )

    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Archivo adjunto no encontrado.",
        )

    file_path = UPLOAD_DIR / attachment.storage_key

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El archivo ya no está disponible.",
        )

    return FileResponse(
        path=file_path,
        filename=attachment.filename,
        media_type=attachment.content_type or "application/octet-stream",
    )


@router.delete(
    "/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_attachment(
    work_item_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_accessible_work_item(db, work_item_id, current_user.id)

    attachment = db.scalar(
        select(WorkItemAttachment).where(
            WorkItemAttachment.id == attachment_id,
            WorkItemAttachment.work_item_id == work_item_id,
        )
    )

    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Archivo adjunto no encontrado.",
        )

    membership = db.get(
        ProjectMember,
        (
            db.get(WorkItem, work_item_id).project_id,
            current_user.id,
        ),
    )

    if (
        attachment.uploaded_by_id != current_user.id
        and membership.role not in ("owner", "admin")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo quien subió el archivo o un administrador puede eliminarlo.",
        )

    file_path = UPLOAD_DIR / attachment.storage_key

    try:
        db.delete(attachment)
        db.commit()
    except Exception:
        db.rollback()
        raise

    file_path.unlink(missing_ok=True)
