from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ECRImageOut(BaseModel):
    id: str
    user_id: str
    deployment_id: str
    repo_name: str
    image_tag: str
    image_uri: str
    size_mb: Optional[float]
    status: str
    pushed_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}

class ECRImageCreate(BaseModel):
    deployment_id: str
    repo_name: str
    image_tag: str
    image_uri: str
    size_mb: Optional[float] = None