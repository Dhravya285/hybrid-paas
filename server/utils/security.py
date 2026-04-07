from datetime import UTC, datetime, timedelta
import os

from jose import jwt

SECRET = os.getenv("JWT_SECRET", "dev-secret")
ALGORITHM = "HS256"
EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))


def create_jwt(payload: dict) -> str:
    claims = payload.copy()
    claims["exp"] = datetime.now(UTC) + timedelta(hours=EXPIRY_HOURS)
    return jwt.encode(claims, SECRET, algorithm=ALGORITHM)
