from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    projects,
    deployments,
    webhooks,
    ecr,
    gitlab_integration,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(deployments.router)
api_router.include_router(webhooks.router)
api_router.include_router(ecr.router)
api_router.include_router(gitlab_integration.router)