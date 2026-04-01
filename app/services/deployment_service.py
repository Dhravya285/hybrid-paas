"""
Deployment orchestrator:
  1. Create/update ECS task definition with the new image
  2. Invoke Lambda (which updates ECS service) OR update service directly
  3. Track deployment status
"""
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import Deployment, DeploymentStatus, Project, BuildConfig
from app.services.aws_service import ecr_service, ecs_service, lambda_service
from app.core.config import settings

logger = logging.getLogger(__name__)


class DeploymentService:

    async def trigger_deployment(
        self,
        db: AsyncSession,
        project_id: UUID,
        image_tag: str,
        commit_sha: str = "",
        commit_message: str = "",
        branch: str = "main",
        triggered_by: str = "manual",
        gitlab_pipeline_id: str = "",
    ) -> Deployment:
        """
        Full deployment flow:
          ECR image → ECS task definition → Lambda → ECS service update
        """
        # Fetch project + build config
        project: Project = await db.get(Project, project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        result = await db.execute(
            select(BuildConfig).where(BuildConfig.project_id == project_id)
        )
        build_config: BuildConfig = result.scalars().first()
        if not build_config:
            raise ValueError(f"No build config for project {project_id}")

        image_uri = f"{project.ecr_repository_uri}:{image_tag}"

        # Create deployment record
        deployment = Deployment(
            project_id=project_id,
            status=DeploymentStatus.DEPLOYING,
            image_tag=image_tag,
            image_uri=image_uri,
            commit_sha=commit_sha,
            commit_message=commit_message,
            branch=branch,
            triggered_by=triggered_by,
            gitlab_pipeline_id=gitlab_pipeline_id,
            started_at=datetime.utcnow(),
        )
        db.add(deployment)
        await db.flush()

        try:
            # 1. Register new ECS task definition
            task_def = ecs_service.register_task_definition(
                family=project.ecs_task_definition or project.name,
                image_uri=image_uri,
                cpu=build_config.cpu,
                memory=build_config.memory,
                port=build_config.port,
                env_vars=[],                        # inject from Environment model if needed
                execution_role_arn=settings.ECS_TASK_EXECUTION_ROLE_ARN,
            )
            task_def_arn = task_def["taskDefinitionArn"]
            logger.info(f"Registered task definition: {task_def_arn}")

            # 2. Invoke Lambda to update ECS service (mirrors EventBridge path)
            lambda_service.invoke_deployer({
                "cluster": settings.ECS_CLUSTER_NAME,
                "service": project.ecs_service_name,
                "taskDefinition": task_def_arn,
                "deploymentId": str(deployment.id),
            })

            deployment.status = DeploymentStatus.SUCCESS
            deployment.ecs_task_arn = task_def_arn

        except Exception as exc:
            logger.error(f"Deployment {deployment.id} failed: {exc}")
            deployment.status = DeploymentStatus.FAILED
            deployment.logs = str(exc)

        finally:
            deployment.finished_at = datetime.utcnow()
            await db.flush()

        return deployment

    async def get_deployment(self, db: AsyncSession, deployment_id: UUID) -> Deployment | None:
        return await db.get(Deployment, deployment_id)

    async def list_deployments(self, db: AsyncSession, project_id: UUID) -> list[Deployment]:
        result = await db.execute(
            select(Deployment)
            .where(Deployment.project_id == project_id)
            .order_by(Deployment.created_at.desc())
            .limit(50)
        )
        return result.scalars().all()

    async def cancel_deployment(self, db: AsyncSession, deployment_id: UUID) -> Deployment | None:
        deployment = await db.get(Deployment, deployment_id)
        if deployment and deployment.status in (DeploymentStatus.PENDING, DeploymentStatus.BUILDING):
            deployment.status = DeploymentStatus.CANCELLED
            deployment.finished_at = datetime.utcnow()
            await db.flush()
        return deployment


deployment_service = DeploymentService()