
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


WorkItemStatus = Literal[
    "todo",
    "in_progress",
    "in_review",
    "done",
    "cancelled",
]

WorkItemPriority = Literal["low", "medium", "high", "urgent"]


class WorkItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: WorkItemStatus = "todo"
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


class WorkItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: str
    description: str | None
    status: str
    priority: str
    reporter_id: int
    assignee_id: int | None
    due_date: datetime | None
    created_at: datetime
    updated_at: datetime
