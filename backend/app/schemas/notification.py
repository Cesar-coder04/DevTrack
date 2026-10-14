
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    type: str
    title: str
    message: str | None
    related_work_item_id: int | None
    is_read: bool
    created_at: datetime
    read_at: datetime | None
