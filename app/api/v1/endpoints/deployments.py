from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.schemas import DeploymentRead, DeploymentTrigger
from app.services.deployment_service import deployment_service

router = APIRouter(prefix="/projects/{project_id}/deployments", tags=["Deployments"])


@router.post("/", response_model=DeploymentRead, status_code=status.HTTP_201_CREATED)
async def trigger_deployment(
    project_id: UUID,
    data: DeploymentTrigger,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    """Manually trigger a deployment for a specific project."""
    deployment = await deployment_service.trigger_deployment(
        db=db,
        project_id=project_id,
        image_tag=data.image_tag or "latest",
        branch=data.branch or "main",
        triggered_by="manual",
    )
    return deployment


@router.get("/", response_model=list[DeploymentRead])
async def list_deployments(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    return await deployment_service.list_deployments(db, project_id)


@router.get("/{deployment_id}", response_model=DeploymentRead)
async def get_deployment(
    project_id: UUID,
    deployment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    deployment = await deployment_service.get_deployment(db, deployment_id)
    if not deployment or deployment.project_id != project_id:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return deployment


@router.post("/{deployment_id}/cancel", response_model=DeploymentRead)
async def cancel_deployment(
    project_id: UUID,
    deployment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    deployment = await deployment_service.cancel_deployment(db, deployment_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found or cannot be cancelled")
    return deployment