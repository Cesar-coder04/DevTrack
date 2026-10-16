
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.project_access import require_project_organization_membership
from app.db.session import get_db
from app.models.user import User
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.tag import Tag
from app.schemas.tag import TagCreate, TagUpdate, TagResponse

from sqlalchemy.exc import IntegrityError

router = APIRouter(
    prefix="/projects/{project_id}/tags",
    tags=["Tags"],
)


def get_project_for_member(
    db: Session,
    project_id: int,
    user: User,
) -> Project:
    project = db.get(Project, project_id)

    if project is None or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado.")

    require_project_organization_membership(
        db,
        project,
        user.id,
        detail="No tienes acceso a este proyecto.",
    )

    membership = db.get(ProjectMember, (project_id, user.id))

    if membership is None:
        raise HTTPException(
            status_code=403,
            detail="No tienes acceso a este proyecto.",
        )

    return project


def ensure_project_not_archived(project: Project) -> None:
    if project.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se pueden modificar etiquetas de un proyecto archivado.",
        )



@router.post("/", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
def create_tag(
    project_id: int,
    data: TagCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_member(db, project_id, user)

    existing = db.scalar(
        select(Tag).where(
            Tag.project_id == project_id,
            Tag.name == data.name,
        )
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Ya existe una etiqueta con ese nombre en el proyecto.",
        )

    tag = Tag(
        project_id=project_id,
        name=data.name,
        color=data.color,
    )

    try:
        db.add(tag)
        db.commit()
        db.refresh(tag)
    except IntegrityError as exc:
        db.rollback()

        error_message = str(exc.orig)

        if (
            getattr(exc.orig, "errno", None) == 1062
            and "uq_tags_project_id_name" in error_message
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe una etiqueta con ese nombre en el proyecto.",
            ) from exc

        raise
    except Exception:
        db.rollback()
        raise

    return tag


@router.get("/", response_model=list[TagResponse])
def list_tags(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_member(db, project_id, user)

    return db.scalars(
        select(Tag)
        .where(Tag.project_id == project_id)
        .order_by(Tag.name.asc())
    ).all()


@router.patch("/{tag_id}", response_model=TagResponse)
def update_tag(
    project_id: int,
    tag_id: int,
    data: TagUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_member(db, project_id, user)
    tag = db.get(Tag, tag_id)

    if tag is None or tag.project_id != project_id:
        raise HTTPException(status_code=404, detail="Etiqueta no encontrada.")

    if data.name is not None:
        existing = db.scalar(
            select(Tag).where(
                Tag.project_id == project_id,
                Tag.name == data.name,
                Tag.id != tag_id,
            )
        )

        if existing:
            raise HTTPException(
                status_code=409,
                detail="Ya existe una etiqueta con ese nombre.",
            )

        tag.name = data.name

    if data.color is not None:
        tag.color = data.color

    try:
        db.commit()
        db.refresh(tag)
    except IntegrityError as exc:
        db.rollback()

        error_message = str(exc.orig)

        if (
            getattr(exc.orig, "errno", None) == 1062
            and "uq_tags_project_id_name" in error_message
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe una etiqueta con ese nombre.",
            ) from exc

        raise
    except Exception:
        db.rollback()
        raise

    return tag


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(
    project_id: int,
    tag_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project_for_member(db, project_id, user)
    membership = db.get(ProjectMember, (project_id, user.id))

    if membership.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Solo el propietario o un administrador puede borrar etiquetas.",
        )

    tag = db.get(Tag, tag_id)

    if tag is None or tag.project_id != project_id:
        raise HTTPException(status_code=404, detail="Etiqueta no encontrada.")

    try:
        db.delete(tag)
        db.commit()
    except Exception:
        db.rollback()
        raise
