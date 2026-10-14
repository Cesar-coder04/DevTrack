
from typing import Literal

from pydantic import BaseModel, Field


class ProjectMemberCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    role: Literal["admin", "member", "viewer"] = "member"


class ProjectMemberRoleUpdate(BaseModel):
    role: Literal["admin", "member", "viewer"]


class ProjectMemberResponse(BaseModel):
    project_id: int
    user_id: int
    username: str
    display_name: str
    role: str
