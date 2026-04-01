"""
Project service – CRUD + AWS + GitLab provisioning when a project is created.
"""
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import Project, BuildConfig, ProjectStatus
from app.schemas.schemas import ProjectCreate, ProjectUpdate, BuildConfigCreate
from app.services.aws_service import ecr_service, eventbridge_service
from app.services.gitlab_service import gitlab_service
from app.core.config import settings

logger = logging.getLogger(__name__)


class ProjectService:

    async def create_project(
        self,
        db: AsyncSession,
        data: ProjectCreate,
        owner_id: UUID,
    ) -> Project:
        # 1. Create DB record
        project = Project(
            name=data.name,
            description=data.description,
            owner_id=owner_id,
            gitlab_repo_url=data.gitlab_repo_url,
        )
        db.add(project)
        await db.flush()           # get project.id

        # 2. Create ECR repository
        ecr_repo_name = f"paas-{project.id}"
        ecr_repo = ecr_service.create_repository(ecr_repo_name)
        project.ecr_repository_name = ecr_repo_name
        project.ecr_repository_uri  = ecr_repo["repositoryUri"]

        # 3. Set ECS identifiers
        project.ecs_service_name    = f"svc-{project.id}"
        project.ecs_task_definition = f"task-{project.id}"

        # 4. Create EventBridge rule for ECR push events
        try:
            rule_name = f"ecr-push-{project.id}"
            eventbridge_service.put_rule(rule_name, ecr_repo["repositoryArn"])
            logger.info(f"EventBridge rule created: {rule_name}")
        except Exception as e:
            logger.warning(f"EventBridge rule creation skipped: {e}")

        # 5. Default build config
        build_config = BuildConfig(project_id=project.id)
        db.add(build_config)

        # 6. GitLab CI variable provisioning (if repo linked)
        if data.gitlab_repo_url:
            self._link_gitlab(project)

        await db.flush()
        return project

    def _link_gitlab(self, project: Project):
        try:
            # Derive project path from URL
            path = project.gitlab_repo_url.rstrip("/").split("gitlab.com/")[-1]
            gl_project = gitlab_service.get_project(path)
            if gl_project:
                project.gitlab_project_id = str(gl_project.id)
                gitlab_service.provision_ecr_variables(
                    project_id=str(gl_project.id),
                    ecr_registry=settings.ECR_REGISTRY_URL,
                    ecr_repo_name=project.ecr_repository_name,
                    aws_region=settings.AWS_REGION,
                )
        except Exception as e:
            logger.warning(f"GitLab linking skipped: {e}")

    async def get_project(self, db: AsyncSession, project_id: UUID) -> Project | None:
        return await db.get(Project, project_id)

    async def list_projects(self, db: AsyncSession, owner_id: UUID) -> list[Project]:
        result = await db.execute(
            select(Project).where(Project.owner_id == owner_id)
        )
        return result.scalars().all()

    async def update_project(
        self,
        db: AsyncSession,
        project_id: UUID,
        data: ProjectUpdate,
    ) -> Project | None:
        project = await db.get(Project, project_id)
        if not project:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(project, field, value)
        await db.flush()
        return project

    async def delete_project(self, db: AsyncSession, project_id: UUID) -> bool:
        project = await db.get(Project, project_id)
        if not project:
            return False
        # Clean up ECR
        if project.ecr_repository_name:
            ecr_service.delete_repository(project.ecr_repository_name)
        await db.delete(project)
        await db.flush()
        return True

    async def upsert_build_config(
        self,
        db: AsyncSession,
        project_id: UUID,
        data: BuildConfigCreate,
    ) -> BuildConfig:
        result = await db.execute(
            select(BuildConfig).where(BuildConfig.project_id == project_id)
        )
        config = result.scalars().first()
        if config:
            for field, value in data.model_dump().items():
                setattr(config, field, value)
        else:
            config = BuildConfig(project_id=project_id, **data.model_dump())
            db.add(config)
        await db.flush()
        return config


project_service = ProjectService()