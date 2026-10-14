import pytest
from pydantic import ValidationError

from app.schemas.project import ProjectCreate


def test_project_requires_a_name():
    project = ProjectCreate(name="DevTrack")

    assert project.name == "DevTrack"
    assert project.description is None


def test_project_rejects_empty_name():
    with pytest.raises(ValidationError):
        ProjectCreate(name="")
