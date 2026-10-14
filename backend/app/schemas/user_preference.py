
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserPreferenceUpdate(BaseModel):
    theme: str | None = Field(default=None, pattern=r"^(light|dark|system)$")
    language: str | None = Field(default=None, pattern=r"^(es|en)$")
    email_notifications: bool | None = None
    push_notifications: bool | None = None


class UserPreferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    theme: str
    language: str
    email_notifications: bool
    push_notifications: bool
    updated_at: datetime
