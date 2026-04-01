from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.services.aws_service import ecr_service
from app.services.project_service import project_service

router = APIRouter(prefix="/ecr", tags=["ECR"])


@router.get("/projects/{project_id}/images")
async def list_images(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    """List all images in the project's ECR repository."""
    project = await project_service.get_project(db, project_id)
    if not project or str(project.owner_id) != current_user_id:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.ecr_repository_name:
        raise HTTPException(status_code=404, detail="No ECR repo configured")

    images = ecr_service.list_images(project.ecr_repository_name)
    return {"repository": project.ecr_repository_name, "images": images}


@router.get("/projects/{project_id}/auth-token")
async def get_ecr_token(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    """Return a short-lived ECR auth token for docker login."""
    token_data = ecr_service.get_authorization_token()
    return {
        "authorizationToken": token_data["authorizationToken"],
        "expiresAt": str(token_data["expiresAt"]),
        "proxyEndpoint": token_data["proxyEndpoint"],
    }