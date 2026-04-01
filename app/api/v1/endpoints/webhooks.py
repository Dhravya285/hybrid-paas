"""
Webhook handlers:
  POST /webhooks/gitlab   – receives GitLab push events, triggers CI/CD
  POST /webhooks/ecr      – receives EventBridge ECR push events, starts ECS deploy
"""
import hashlib
import hmac
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.models.models import Project
from app.services.deployment_service import deployment_service
from app.services.gitlab_service import gitlab_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def _verify_gitlab_signature(request_body: bytes, token: str) -> bool:
    """GitLab uses a plain-token header, not HMAC – just compare."""
    return hmac.compare_digest(token, settings.GITLAB_WEBHOOK_SECRET)


# ── GitLab push webhook ──────────────────────────────────────────────────────

@router.post("/gitlab", status_code=status.HTTP_202_ACCEPTED)
async def gitlab_push_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    token = request.headers.get("X-Gitlab-Token", "")
    body  = await request.body()

    if not _verify_gitlab_signature(body, token):
        raise HTTPException(status_code=401, detail="Invalid webhook token")

    payload = await request.json()
    object_kind = payload.get("object_kind")

    if object_kind != "push":
        return {"message": "Ignored non-push event"}

    gitlab_project_id = str(payload.get("project", {}).get("id", ""))
    ref    = payload.get("ref", "refs/heads/main")
    branch = ref.split("/")[-1]
    sha    = payload.get("checkout_sha", "")
    msg    = (payload.get("commits") or [{}])[0].get("message", "")

    # Lookup our Project by gitlab_project_id
    result = await db.execute(
        select(Project).where(Project.gitlab_project_id == gitlab_project_id)
    )
    project = result.scalars().first()
    if not project:
        logger.warning(f"No project found for GitLab project ID {gitlab_project_id}")
        return {"message": "Project not tracked"}

    # Trigger pipeline and deployment
    pipeline = gitlab_service.trigger_pipeline(
        project_id=gitlab_project_id,
        ref=branch,
        variables={"TRIGGERED_BY": "webhook"},
    )

    if pipeline:
        await deployment_service.trigger_deployment(
            db=db,
            project_id=project.id,
            image_tag=sha[:8] or "latest",
            commit_sha=sha,
            commit_message=msg,
            branch=branch,
            triggered_by="push",
            gitlab_pipeline_id=str(pipeline.get("id", "")),
        )

    return {"message": "Deployment triggered", "pipeline": pipeline}


# ── EventBridge → ECR push event ─────────────────────────────────────────────

@router.post("/ecr", status_code=status.HTTP_202_ACCEPTED)
async def ecr_event_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    EventBridge forwards ECR image push events here via an HTTP target or API GW.
    Payload: { "source": "aws.ecr", "detail-type": "ECR Image Action", "detail": {...} }
    """
    payload = await request.json()
    detail  = payload.get("detail", {})

    repo_name = detail.get("repository-name", "")
    image_tag = detail.get("image-tag", "latest")
    action    = detail.get("action-type", "")

    if action != "PUSH":
        return {"message": f"Ignored action: {action}"}

    result = await db.execute(
        select(Project).where(Project.ecr_repository_name == repo_name)
    )
    project = result.scalars().first()
    if not project:
        logger.warning(f"No project for ECR repo {repo_name}")
        return {"message": "Repo not tracked"}

    await deployment_service.trigger_deployment(
        db=db,
        project_id=project.id,
        image_tag=image_tag,
        triggered_by="ecr_event",
    )

    return {"message": "ECS deployment triggered", "repo": repo_name, "tag": image_tag}