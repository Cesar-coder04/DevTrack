from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.work_item import WorkItemPriority, WorkItemStatus, WorkItemType


class UserWorkItemResponse(BaseModel):
    id: int
    type: WorkItemType
    title: str
    status: WorkItemStatus
    priority: WorkItemPriority
    project_id: int
    project_name: str
    organization_id: int | None
    organization_name: str | None
    due_date: date | None
    created_at: datetime
    updated_at: datetime


class UserIssueResponse(BaseModel):
    id: int
    type: Literal["issue"]
    title: str
    description: str | None
    status: WorkItemStatus
    priority: WorkItemPriority
    assignee_id: int | None
    assignee_display_name: str | None
    project_id: int
    project_name: str
    organization_id: int | None
    organization_name: str | None
    created_at: datetime
    updated_at: datetime
