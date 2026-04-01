from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.services.gitlab_service import gitlab_service
from app.services.project_service import project_service
from app.core.config import settings

router = APIRouter(prefix="/gitlab", tags=["GitLab"])


class RepoConnectRequest(BaseModel):
    gitlab_repo_url: str
    webhook_url: str        # publicly reachable URL for this backend


class PipelineTriggerRequest(BaseModel):
    ref: str = "main"
    variables: dict = {}


@router.post("/projects/{project_id}/connect")
async def connect_repo(
    project_id: UUID,
    data: RepoConnectRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    """Connect a GitLab repo to a project, provision CI vars and webhook."""
    project = await project_service.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    path = data.gitlab_repo_url.rstrip("/").split("gitlab.com/")[-1]
    gl_project = gitlab_service.get_project(path)
    if not gl_project:
        raise HTTPException(status_code=404, detail="GitLab project not found")

    project.gitlab_repo_url    = data.gitlab_repo_url
    project.gitlab_project_id  = str(gl_project.id)
    await db.flush()

    gitlab_service.provision_ecr_variables(
        project_id=str(gl_project.id),
        ecr_registry=settings.ECR_REGISTRY_URL,
        ecr_repo_name=project.ecr_repository_name or "",
        aws_region=settings.AWS_REGION,
    )

    webhook = gitlab_service.create_push_webhook(
        project_id=str(gl_project.id),
        webhook_url=f"{data.webhook_url}/api/v1/webhooks/gitlab",
    )

    return {
        "gitlab_project_id": gl_project.id,
        "webhook": webhook,
        "ci_variables_set": ["ECR_REGISTRY", "ECR_REPOSITORY", "AWS_DEFAULT_REGION"],
    }


@router.get("/projects/{project_id}/branches")
async def list_branches(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    project = await project_service.get_project(db, project_id)
    if not project or not project.gitlab_project_id:
        raise HTTPException(status_code=404, detail="GitLab repo not connected")
    return gitlab_service.list_branches(project.gitlab_project_id)


@router.post("/projects/{project_id}/pipeline")
async def trigger_pipeline(
    project_id: UUID,
    data: PipelineTriggerRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    project = await project_service.get_project(db, project_id)
    if not project or not project.gitlab_project_id:
        raise HTTPException(status_code=404, detail="GitLab repo not connected")
    result = gitlab_service.trigger_pipeline(
        project_id=project.gitlab_project_id,
        ref=data.ref,
        variables=data.variables,
    )
    return result


@router.get("/projects/{project_id}/ci-template")
async def get_ci_template(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    """Return a ready-to-commit .gitlab-ci.yml for this project."""
    project = await project_service.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    template = gitlab_service.generate_ci_template(
        ecr_registry=settings.ECR_REGISTRY_URL,
        ecr_repo=project.ecr_repository_name or "your-repo",
        region=settings.AWS_REGION,
    )
    return {"template": template}