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


def test_project_rejects_name_containing_only_whitespace():
    with pytest.raises(ValidationError):
        ProjectCreate(name="   ")


def test_project_accepts_name_with_100_characters():
    name = "a" * 100

    project = ProjectCreate(name=name)

    assert project.name == name


def test_project_rejects_name_with_101_characters():
    with pytest.raises(ValidationError):
        ProjectCreate(name="a" * 101)


def test_project_preserves_valid_name_with_surrounding_whitespace():
    name = "  DevTrack  "

    project = ProjectCreate(name=name)

    assert project.name == name
