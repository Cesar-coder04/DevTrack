
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WorkItemAttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_item_id: int
    uploaded_by: int
    file_name: str
    storage_key: str
    content_type: str | None
    size_bytes: int
    created_at: datetime
