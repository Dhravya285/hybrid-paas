import uuid
from datetime import datetime
from sqlalchemy import (
    String, Text, Boolean, DateTime, ForeignKey, Enum as SAEnum, JSON, Integer
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.core.database import Base


# ──────────────────────────────────────────
# Enums
# ──────────────────────────────────────────

class DeploymentStatus(str, enum.Enum):
    PENDING   = "pending"
    BUILDING  = "building"
    PUSHING   = "pushing"
    DEPLOYING = "deploying"
    SUCCESS   = "success"
    FAILED    = "failed"
    CANCELLED = "cancelled"


class ProjectStatus(str, enum.Enum):
    ACTIVE   = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class EnvironmentType(str, enum.Enum):
    PRODUCTION  = "production"
    STAGING     = "staging"
    PREVIEW     = "preview"


# ──────────────────────────────────────────
# Models
# ──────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str]           = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str]        = mapped_column(String(100), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool]      = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool]       = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    projects: Mapped[list["Project"]] = relationship("Project", back_populates="owner", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str]               = mapped_column(String(100), nullable=False)
    description: Mapped[str]        = mapped_column(Text, nullable=True)
    owner_id: Mapped[uuid.UUID]     = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status: Mapped[ProjectStatus]   = mapped_column(SAEnum(ProjectStatus), default=ProjectStatus.ACTIVE)
    gitlab_repo_url: Mapped[str]    = mapped_column(String(500), nullable=True)
    gitlab_project_id: Mapped[str]  = mapped_column(String(100), nullable=True)
    ecr_repository_name: Mapped[str] = mapped_column(String(255), nullable=True)
    ecr_repository_uri: Mapped[str] = mapped_column(String(500), nullable=True)
    ecs_service_name: Mapped[str]   = mapped_column(String(255), nullable=True)
    ecs_task_definition: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime]    = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime]    = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner: Mapped["User"]                    = relationship("User", back_populates="projects")
    environments: Mapped[list["Environment"]] = relationship("Environment", back_populates="project", cascade="all, delete-orphan")
    deployments: Mapped[list["Deployment"]]   = relationship("Deployment", back_populates="project", cascade="all, delete-orphan")
    build_configs: Mapped[list["BuildConfig"]] = relationship("BuildConfig", back_populates="project", cascade="all, delete-orphan")


class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[uuid.UUID]              = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    name: Mapped[str]                  = mapped_column(String(100), nullable=False)
    env_type: Mapped[EnvironmentType]  = mapped_column(SAEnum(EnvironmentType), default=EnvironmentType.PREVIEW)
    env_vars: Mapped[dict]             = mapped_column(JSON, default=dict)   # stored encrypted in prod
    domain: Mapped[str]                = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime]       = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="environments")


class BuildConfig(Base):
    __tablename__ = "build_configs"

    id: Mapped[uuid.UUID]         = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    branch: Mapped[str]           = mapped_column(String(255), default="main")
    dockerfile_path: Mapped[str]  = mapped_column(String(500), default="Dockerfile")
    build_args: Mapped[dict]      = mapped_column(JSON, default=dict)
    cpu: Mapped[str]              = mapped_column(String(10), default="256")   # ECS Fargate CPU units
    memory: Mapped[str]           = mapped_column(String(10), default="512")   # MB
    port: Mapped[int]             = mapped_column(Integer, default=8080)
    health_check_path: Mapped[str] = mapped_column(String(255), default="/health")
    auto_deploy: Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime]  = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime]  = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="build_configs")


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[uuid.UUID]            = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    status: Mapped[DeploymentStatus] = mapped_column(SAEnum(DeploymentStatus), default=DeploymentStatus.PENDING)
    image_tag: Mapped[str]           = mapped_column(String(255), nullable=True)
    image_uri: Mapped[str]           = mapped_column(String(500), nullable=True)
    commit_sha: Mapped[str]          = mapped_column(String(100), nullable=True)
    commit_message: Mapped[str]      = mapped_column(Text, nullable=True)
    branch: Mapped[str]              = mapped_column(String(255), nullable=True)
    triggered_by: Mapped[str]        = mapped_column(String(100), nullable=True)   # "push" | "manual" | "ecr_event"
    gitlab_pipeline_id: Mapped[str]  = mapped_column(String(100), nullable=True)
    ecs_task_arn: Mapped[str]        = mapped_column(String(500), nullable=True)
    logs: Mapped[str]                = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime]     = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime]    = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime]     = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="deployments")