from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from config.db import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    owner = Column(String, nullable=False)
    repo = Column(String, nullable=False)
    branch = Column(String, nullable=False)
    source_dir = Column(String, nullable=False, default="/")
    repository_uri = Column(String, nullable=False)
    image_tag = Column(String, nullable=False)
    image_uri = Column(String, nullable=False)
    status = Column(String, nullable=False, default="running")
    public_url = Column(String, nullable=True)
    ecs_service_name = Column(String, nullable=True)
    ecs_task_definition_arn = Column(String, nullable=True)
    ecs_target_group_arn = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
