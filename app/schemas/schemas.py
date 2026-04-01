from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field

from app.models.models import DeploymentStatus, ProjectStatus, EnvironmentType


# ──────────────────────────────────────────
# Auth
# ──────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)


class UserRead(BaseModel):
    id: UUID
    email: str
    username: str
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[str] = None


# ──────────────────────────────────────────
# Project
# ──────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    gitlab_repo_url: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None
    gitlab_repo_url: Optional[str] = None


class ProjectRead(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    status: ProjectStatus
    owner_id: UUID
    gitlab_repo_url: Optional[str]
    gitlab_project_id: Optional[str]
    ecr_repository_name: Optional[str]
    ecr_repository_uri: Optional[str]
    ecs_service_name: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


# ──────────────────────────────────────────
# Build Config
# ──────────────────────────────────────────

class BuildConfigCreate(BaseModel):
    branch: str = "main"
    dockerfile_path: str = "Dockerfile"
    build_args: Dict[str, Any] = {}
    cpu: str = "256"
    memory: str = "512"
    port: int = 8080
    health_check_path: str = "/health"
    auto_deploy: bool = True


class BuildConfigRead(BuildConfigCreate):
    id: UUID
    project_id: UUID
    created_at: datetime
    model_config = {"from_attributes": True}


# ──────────────────────────────────────────
# Environment
# ──────────────────────────────────────────

class EnvironmentCreate(BaseModel):
    name: str
    env_type: EnvironmentType = EnvironmentType.PREVIEW
    env_vars: Dict[str, str] = {}
    domain: Optional[str] = None


class EnvironmentRead(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    env_type: EnvironmentType
    domain: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


# ──────────────────────────────────────────
# Deployment
# ──────────────────────────────────────────

class DeploymentTrigger(BaseModel):
    branch: Optional[str] = "main"
    image_tag: Optional[str] = None


class DeploymentRead(BaseModel):
    id: UUID
    project_id: UUID
    status: DeploymentStatus
    image_tag: Optional[str]
    image_uri: Optional[str]
    commit_sha: Optional[str]
    commit_message: Optional[str]
    branch: Optional[str]
    triggered_by: Optional[str]
    gitlab_pipeline_id: Optional[str]
    ecs_task_arn: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime
    model_config = {"from_attributes": True}


# ──────────────────────────────────────────
# Webhook payloads
# ──────────────────────────────────────────

class GitLabWebhookPush(BaseModel):
    object_kind: str
    ref: str
    checkout_sha: Optional[str] = None
    commits: List[Dict[str, Any]] = []
    project: Dict[str, Any] = {}


class EventBridgeECRPayload(BaseModel):
    source: str
    detail_type: str = Field(alias="detail-type")
    detail: Dict[str, Any]
    model_config = {"populate_by_name": True}