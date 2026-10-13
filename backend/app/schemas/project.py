from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None
    status: str
    created_at: datetime
