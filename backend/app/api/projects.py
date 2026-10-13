from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.schemas.project import ProjectResponse

from app.models.project import Project

from app.db.session import get_db

router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
)


@router.get("/", response_model=list[ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    query = select(Project)
    result = db.execute(query)
    projects = result.scalars().all()

    return projects

