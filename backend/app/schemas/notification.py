
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int = Field(validation_alias="recipient_id")
    type: str
    title: str
    message: str | None
    related_work_item_id: int | None = Field(
        validation_alias="work_item_id"
    )
    is_read: bool
    created_at: datetime
    read_at: datetime | None
