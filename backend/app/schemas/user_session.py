
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    ip_address: str | None
    user_agent: str | None
