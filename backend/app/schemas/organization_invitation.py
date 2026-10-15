
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

InvitationRole = Literal["admin", "member"]
InvitationStatus = Literal[
    "pending",
    "accepted",
    "revoked",
    "expired",
]


class OrganizationInvitationCreate(BaseModel):
    email: EmailStr
    role: InvitationRole = "member"


class OrganizationInvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    invited_by: int = Field(validation_alias="invited_by_id")
    email: EmailStr
    role: InvitationRole
    status: InvitationStatus
    expires_at: datetime
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def derive_status_from_timestamps(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return value

        accepted_at = value.accepted_at
        revoked_at = value.revoked_at
        expires_at = value.expires_at
        normalized_expiry = expires_at
        if normalized_expiry.tzinfo is None:
            normalized_expiry = normalized_expiry.replace(tzinfo=timezone.utc)
        else:
            normalized_expiry = normalized_expiry.astimezone(timezone.utc)

        if accepted_at is not None:
            invitation_status = "accepted"
        elif revoked_at is not None:
            invitation_status = "revoked"
        elif normalized_expiry <= datetime.now(timezone.utc):
            invitation_status = "expired"
        else:
            invitation_status = "pending"

        return {
            "id": value.id,
            "organization_id": value.organization_id,
            "invited_by_id": value.invited_by_id,
            "email": value.email,
            "role": value.role,
            "status": invitation_status,
            "expires_at": expires_at,
            "created_at": value.created_at,
        }


class OrganizationInvitationDecision(BaseModel):
    action: Literal["accept", "reject"]
