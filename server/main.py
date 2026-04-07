from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"message": "status running"}


app.include_router(auth_router)
app.include_router(repo_router)
