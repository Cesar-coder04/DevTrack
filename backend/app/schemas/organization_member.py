
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OrganizationMemberCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    role: Literal["admin", "member"] = "member"


class OrganizationMemberRoleUpdate(BaseModel):
    role: Literal["admin", "member"]


class OrganizationMemberResponse(BaseModel):
    user_id: int
    username: str
    display_name: str
    role: str
    joined_at: datetime | None = None
