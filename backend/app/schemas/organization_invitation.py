
from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr

InvitationRole = Literal["admin", "member", "viewer"]
InvitationStatus = Literal[
    "pending",
    "accepted",
    "rejected",
    "expired",
]

class OrganizationInvitationCreate(BaseModel):
    email: EmailStr
    role: InvitationRole = "member"

class OrganizationInvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    invited_by: int
    email: EmailStr
    role: InvitationRole
    status: InvitationStatus
    expires_at: datetime
    created_at: datetime


class OrganizationInvitationDecision(BaseModel):
    action: Literal["accept", "reject"]
