
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkItemAttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_item_id: int
    uploaded_by: int = Field(validation_alias="uploaded_by_id")
    file_name: str = Field(validation_alias="filename")
    content_type: str | None
    size_bytes: int
    created_at: datetime = Field(validation_alias="uploaded_at")
