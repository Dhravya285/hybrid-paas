import uuid
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.db import get_db
from config.main import settings
from models.user import User
from schemas.user import GitHubCallbackRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer()

GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL  = "https://api.github.com/user"


def create_jwt(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(days=7),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(
            credentials.credentials, settings.jwt_secret, algorithms=["HS256"]
        )
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user



@router.post("/auth/github/callback")
async def github_callback(body: GitHubCallbackRequest, db: AsyncSession = Depends(get_db)):
    # NextAuth already exchanged the code — body.code IS the access token
    access_token = body.code

    # fetch GitHub profile directly
    async with httpx.AsyncClient() as client:
        user_res = await client.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    gh = user_res.json()

    # 3. Upsert user row
    result = await db.execute(
        select(User).where(User.github_id == str(gh["id"]))
    )
    user = result.scalar_one_or_none()

    if user:
        user.email        = gh.get("email")
        user.name         = gh.get("name") or gh["login"]
        user.avatar_url   = gh.get("avatar_url")
        user.github_username = gh["login"]
        user.updated_at   = datetime.utcnow()
    else:
        user = User(
            id               = str(uuid.uuid4()),
            github_id        = str(gh["id"]),
            email            = gh.get("email"),
            name             = gh.get("name") or gh["login"],
            avatar_url       = gh.get("avatar_url"),
            github_username  = gh["login"],
        )
        db.add(user)

    await db.flush()   # get the id before commit

    token = create_jwt(user.id)
    return {"access_token": token, "user": UserOut.model_validate(user)}
    token = create_jwt(user.id)
    print("=== TOKEN ===")
    print(token)
    print("=============")
    return {"access_token": token, "user": UserOut.model_validate(user)}


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user