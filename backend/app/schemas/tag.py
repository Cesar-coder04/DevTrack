
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TagNameBase(BaseModel):
    name: str = Field(min_length=1, max_length=50)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class TagCreate(TagNameBase):
    color: str = Field(
        default="#808080",
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )


class TagUpdate(TagNameBase):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )
    color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )


class TagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    color: str
    created_at: datetime
