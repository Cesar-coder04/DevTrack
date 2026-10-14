
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrganizationProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class OrganizationProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)


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
