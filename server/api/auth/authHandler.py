from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import requests

from sqlalchemy.orm import Session
from config.db import get_db
from models.users import User
from utils.security import create_jwt

router = APIRouter()

class GitHubAuthRequest(BaseModel):
    access_token: str


@router.post("/auth/github")
async def github_auth(
    body: GitHubAuthRequest,
    db: Session = Depends(get_db)
):
    token = body.access_token

    user_res = requests.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )

    if user_res.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid GitHub token")

    user_data = user_res.json()

    github_id = str(user_data["id"])
    username = user_data["login"]
    avatar = user_data.get("avatar_url")

    email_res = requests.get(
        "https://api.github.com/user/emails",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )

    email = None
    if email_res.status_code == 200:
        emails = email_res.json()
        primary = next((e for e in emails if e["primary"]), None)
        if primary:
            email = primary["email"]

    user = db.query(User).filter(User.github_id == github_id).first()

    if not user:
        user = User(
            github_id=github_id,
            username=username,
            email=email,
            avatar=avatar,
            github_access_token=token  
        )
        db.add(user)
    else:
        user.github_access_token = token
        user.username = username
        user.email = email
        user.avatar = avatar

    db.commit()
    db.refresh(user)

    jwt_token = create_jwt({
        "user_id": user.id,
        "github_id": user.github_id
    })

    return {
        "access_token": jwt_token,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "avatar": user.avatar
        }
    }
