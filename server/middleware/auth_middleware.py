from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt, JWTError
import os

SECRET = os.getenv("JWT_SECRET", "dev-secret")
ALGORITHM = "HS256"


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        public_paths = ["/auth/github", "/docs", "/openapi.json", "/health", "/deployments/aws-callback"]

        if request.url.path in public_paths:
            return await call_next(request)

        auth_header = request.headers.get("Authorization")

        if not auth_header:
            raise HTTPException(status_code=401, detail="Missing Authorization header")

        try:
            token = auth_header.split(" ")[1]
        except IndexError:
            raise HTTPException(status_code=401, detail="Invalid Authorization format")

        try:
            payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
            request.state.user_id = payload.get("user_id")

            if not request.state.user_id:
                raise HTTPException(status_code=401, detail="Invalid token payload")

        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        response = await call_next(request)
        return response
