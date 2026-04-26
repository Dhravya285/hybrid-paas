from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from api.auth.authHandler import router as auth_router
from api.repo.repo_router import router as repo_router
from config.db import Base, eng
from middleware.auth_middleware import AuthMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=eng)
    ensure_deployment_columns()


def ensure_deployment_columns() -> None:
    inspector = inspect(eng)
    if "deployments" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("deployments")}
    columns = {
        "public_url": "VARCHAR",
        "ecs_service_name": "VARCHAR",
        "ecs_task_definition_arn": "VARCHAR",
        "ecs_target_group_arn": "VARCHAR",
    }

    with eng.begin() as connection:
        for column_name, column_type in columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(f"ALTER TABLE deployments ADD COLUMN {column_name} {column_type}")
                )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"message": "status running"}


app.include_router(auth_router)
app.include_router(repo_router)
