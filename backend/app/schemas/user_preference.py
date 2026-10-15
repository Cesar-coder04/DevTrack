
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class UserPreferenceUpdate(BaseModel):
    theme: str | None = Field(default=None, pattern=r"^(light|dark|system)$")
    language: str | None = Field(default=None, pattern=r"^(es|en)$")
    email_notifications: bool | None = None
    push_notifications: bool | None = None

    @field_validator(
        "theme",
        "language",
        "email_notifications",
        "push_notifications",
        mode="before",
    )
    @classmethod
    def reject_null_updates(cls, value):
        if value is None:
            raise ValueError("Las preferencias enviadas no pueden ser null.")
        return value


class UserPreferenceResponse(BaseModel):
    user_id: int
    theme: str = "system"
    language: str = "es"
    email_notifications: bool
    push_notifications: bool = False
    updated_at: datetime
