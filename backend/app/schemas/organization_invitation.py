
from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr


class OrganizationInvitationCreate(BaseModel):
    email: EmailStr
    role: Literal["admin", "member", "viewer"] = "member"


class OrganizationInvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    invited_by: int
    email: EmailStr
    role: str
    status: str
    expires_at: datetime
    created_at: datetime


class OrganizationInvitationDecision(BaseModel):
    action: Literal["accept", "reject"]
