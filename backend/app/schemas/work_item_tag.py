
from pydantic import BaseModel


class WorkItemTagCreate(BaseModel):
    tag_id: int


class WorkItemTagResponse(BaseModel):
    id: int
    name: str
    color: str
