import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.db import get_db
from models.ecr_image import ECRImage
from models.user import User
from routes.auth import get_current_user
from schemas.ecr_image import ECRImageCreate, ECRImageOut

router = APIRouter(prefix="/ecr", tags=["ecr"])


@router.post("/images", response_model=ECRImageOut)
async def push_image(
    body: ECRImageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    image = ECRImage(
        id            = str(uuid.uuid4()),
        user_id       = current_user.id,
        deployment_id = body.deployment_id,
        repo_name     = body.repo_name,
        image_tag     = body.image_tag,
        image_uri     = body.image_uri,
        size_mb       = body.size_mb,
    )
    db.add(image)
    await db.flush()
    return ECRImageOut.model_validate(image)


@router.get("/images", response_model=list[ECRImageOut])
async def list_images(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ECRImage)
        .where(ECRImage.user_id == current_user.id)
        .order_by(ECRImage.pushed_at.desc())
    )
    return [ECRImageOut.model_validate(r) for r in result.scalars().all()]


@router.get("/images/deployment/{deployment_id}", response_model=ECRImageOut)
async def get_by_deployment(
    deployment_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ECRImage).where(ECRImage.deployment_id == deployment_id)
    )
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    if image.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return ECRImageOut.model_validate(image)


@router.patch("/images/{image_id}/status", response_model=ECRImageOut)
async def set_status(
    image_id: str,
    status: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ECRImage).where(ECRImage.id == image_id))
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    if image.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    image.status     = status
    image.updated_at = datetime.utcnow()
    await db.flush()
    return ECRImageOut.model_validate(image)