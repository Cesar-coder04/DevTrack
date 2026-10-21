from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


WorkItemStatus = Literal[
    "open",
    "in_progress",
    "resolved",
    "closed",
]

WorkItemPriority = Literal["low", "medium", "high", "urgent"]


class WorkItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: WorkItemStatus = "open"
    priority: WorkItemPriority = "medium"
    assignee_id: int | None = None
    due_date: datetime | None = None


class WorkItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: WorkItemStatus | None = None
    priority: WorkItemPriority | None = None
    assignee_id: int | None = None
    due_date: datetime | None = None

    @field_validator("status", mode="before")
    @classmethod
    def reject_null_status(cls, value):
        if value is None:
            raise ValueError("El estado no puede ser null.")
        return value

    @field_validator("title", "priority", mode="before")
    @classmethod
    def reject_null_non_nullable_fields(cls, value):
        if value is None:
            raise ValueError("Este campo no puede ser null.")
        return value


class WorkItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: str
    description: str | None
    status: WorkItemStatus
    priority: str
    reporter_id: int = Field(validation_alias="created_by_id")
    assignee_id: int | None = Field(validation_alias="assigned_to_id")
    due_date: datetime | None
    created_at: datetime
    updated_at: datetime


class WorkItemListResponse(WorkItemResponse):
    assignee_display_name: str | None = None
