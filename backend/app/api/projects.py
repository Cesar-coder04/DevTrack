from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.schemas.project import ProjectResponse
from app.schemas.project import ProjectCreate
from sqlalchemy.exc import SQLAlchemyError

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




@router.post("/", response_model=ProjectResponse, status_code=201)
def create_project(
    project: ProjectCreate,
    db: Session = Depends(get_db),
):
    try:
        db_project = Project(**project.model_dump())
        db.add(db_project)
        db.commit()
        db.refresh(db_project)

        return db_project

    
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="An error occurred while creating the project.",
        ) from None




