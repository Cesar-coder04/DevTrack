
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkItemHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_item_id: int
    user_id: int = Field(validation_alias="changed_by_id")
    field_name: str
    old_value: str | None
    new_value: str | None
    created_at: datetime = Field(validation_alias="changed_at")
