
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProjectMemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=50)
    role: Literal["admin", "member", "viewer"] = "member"


class ProjectMemberRoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["admin", "member", "viewer"]


class ProjectMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: int
    user_id: int
    username: str
    display_name: str
    role: str
