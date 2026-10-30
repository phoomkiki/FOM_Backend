"""Security helpers. Authentication endpoints are scaffolding, not production-ready yet."""
from datetime import datetime, timedelta, timezone
from jose import jwt
from app.core.config import settings

ALGORITHM = "HS256"

def create_access_token(subject: str, role: str | None = None) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    claims = {"sub": subject, "exp": expires}
    if role is not None:
        claims["role"] = role
    return jwt.encode(claims, settings.secret_key, algorithm=ALGORITHM)
