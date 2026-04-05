from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class UserOut(BaseModel):
    id: str
    github_id: str
    email: Optional[str]
    name: str
    avatar_url: Optional[str]
    github_username: str
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}

class GitHubCallbackRequest(BaseModel):
    code: str