
from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)


ProjectName = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=100,
        strip_whitespace=True,
    ),
]


class OrganizationProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ProjectName
    description: str | None = Field(default=None, max_length=500)


class OrganizationProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ProjectName | None = None
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("El nombre no puede ser nulo.")
        return value


class OrganizationProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    status: str
    organization_id: int
    owner_id: int
    visibility: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
