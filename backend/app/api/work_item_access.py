from fastapi import HTTPException, status

from app.models.work_item import WorkItem


def ensure_work_item_active(item: WorkItem) -> None:
    if item.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tarea no encontrada.",
        )
