from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def reject_whitespace_only_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("El nombre no puede estar vacío.")
        return value


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None
    status: str
    created_at: datetime
    organization_name: str | None = None
