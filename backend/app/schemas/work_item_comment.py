
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkItemCommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class WorkItemCommentUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class WorkItemCommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_item_id: int
    user_id: int
    content: str
    created_at: datetime
    updated_at: datetime | None = None
