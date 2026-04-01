from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.schemas import ProjectCreate, ProjectRead, ProjectUpdate, BuildConfigCreate, BuildConfigRead
from app.services.project_service import project_service

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post("/", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    project = await project_service.create_project(db, data, UUID(current_user_id))
    return project


@router.get("/", response_model=list[ProjectRead])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    return await project_service.list_projects(db, UUID(current_user_id))


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    project = await project_service.get_project(db, project_id)
    if not project or str(project.owner_id) != current_user_id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    project = await project_service.update_project(db, project_id, data)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    deleted = await project_service.delete_project(db, project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")


# ── Build Config ──────────────────────────────

@router.put("/{project_id}/build-config", response_model=BuildConfigRead)
async def upsert_build_config(
    project_id: UUID,
    data: BuildConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    return await project_service.upsert_build_config(db, project_id, data)