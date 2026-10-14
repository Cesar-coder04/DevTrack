
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WorkItemHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_item_id: int
    user_id: int
    field_name: str
    old_value: str | None
    new_value: str | None
    created_at: datetime
