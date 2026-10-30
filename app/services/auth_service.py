"""Business logic for LINE authentication and FOM user sessions."""

from datetime import datetime, timezone
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import settings
from app.core.security import ALGORITHM, create_access_token
from app.schemas.auth import AdminLoginRequest, AuthPrincipal, AuthUser, LineLoginRequest, LineLoginResponse
from app.services.data_api import select_rows
from app.services.supabase_rest import (
    create_line_user, find_user_by_line_id, get_user_by_id, update_user_img_url,
    _config, _headers, find_user_by_auth_id,
)

bearer_scheme = HTTPBearer(auto_error=False)


def _public_user(row: dict) -> AuthUser:
    """Build the public user payload using only profile fields.

    The users table has no phone, role or account_status columns. Role is
    authorization context only and is never included in the public user object.
    """
    created_at = row.get("created_at")
    if created_at is not None and not isinstance(created_at, str):
        created_at = str(created_at)
    return AuthUser(
        user_id=row["user_id"], line_user_id=row.get("line_user_id"),
        display_name=row["display_name"], img_url=row.get("img_url"),
        phone=None, account_status="active", created_at=created_at,
    )


def _ensure_signing_secret() -> None:
    if settings.secret_key == "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET" or len(settings.secret_key) < 32:
        raise HTTPException(503, "FOM session signing is not configured securely on the server.")


async def _verify_line_id_token(id_token: str) -> dict:
    channel_id = (settings.line_channel_id or "").strip()
    if not channel_id:
        raise HTTPException(503, "LINE login is not configured on the server.")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.line.me/oauth2/v2.1/verify",
                data={"id_token": id_token, "client_id": channel_id},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Could not verify the LINE ID Token.") from exc
    if response.status_code != 200:
        raise HTTPException(401, "The LINE ID Token is invalid or expired.")
    try:
        claims = response.json()
    except ValueError as exc:
        raise HTTPException(502, "LINE returned an invalid verification response.") from exc
    if not claims.get("sub"):
        raise HTTPException(401, "The verified LINE token does not contain a user ID.")
    return claims


async def _resolve_role(row: dict) -> str:
    """Resolve roles without querying columns absent from the current User model."""
    if row.get("role") in {"customer", "owner", "admin"}:
        return row["role"]
    shops = await select_rows(
        "shops", select="shop_id", filters={"owner_id": f"eq.{row['user_id']}"}, limit=1
    )
    return "owner" if shops else "customer"


async def login_with_line(payload: LineLoginRequest) -> LineLoginResponse:
    _ensure_signing_secret()
    claims = await _verify_line_id_token(payload.id_token)
    line_user_id = claims["sub"]
    img_url = claims.get("picture")
    row = await find_user_by_line_id(line_user_id)
    if row is None:
        display_name = (claims.get("name") or "LINE User").strip()[:100] or "LINE User"
        row = await create_line_user(line_user_id, display_name, img_url)
    elif img_url and row.get("img_url") != img_url:
        row = await update_user_img_url(line_user_id, img_url) or row
    return LineLoginResponse(access_token=create_access_token(str(row["user_id"])), user=_public_user(row))


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthPrincipal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "Authentication required.", headers={"WWW-Authenticate": "Bearer"})
    _ensure_signing_secret()
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        expires = payload.get("exp")
        if not subject or expires is None or int(expires) <= int(datetime.now(timezone.utc).timestamp()):
            raise JWTError("Missing or expired token claims")
        user_id = int(subject)
    except (JWTError, TypeError, ValueError) as exc:
        raise HTTPException(401, "Invalid or expired FOM session.", headers={"WWW-Authenticate": "Bearer"}) from exc
    row = await get_user_by_id(user_id)
    if row is None:
        raise HTTPException(401, "The FOM user account no longer exists.")
    # Admin role is embedded only in a server-signed token issued after checking
    # Supabase Auth app_metadata. Owner role is derived from shops.owner_id.
    token_role = payload.get("role")
    if token_role == "admin":
        role = "admin"
    else:
        role = await _resolve_role(row)
    return AuthPrincipal(**_public_user(row).model_dump(), role=role)


async def login_admin(payload: AdminLoginRequest) -> LineLoginResponse:
    """Authenticate a Supabase email/password account and require an active FOM admin."""
    _ensure_signing_secret()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(503, "Supabase Auth is not configured.")
    base_url, key = _config()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{base_url}/auth/v1/token", params={"grant_type": "password"},
                headers=_headers(key), json={"email": payload.email, "password": payload.password},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Could not contact Supabase Auth.") from exc
    if response.status_code != 200:
        raise HTTPException(401, "Invalid email or password.")
    try:
        auth_id = response.json()["user"]["id"]
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(502, "Supabase Auth returned an invalid response.") from exc
    row = await find_user_by_auth_id(auth_id)
    # Role is not stored on public.users. Require an explicit trusted Supabase
    # Auth app_metadata role before issuing an admin session.
    try:
        app_role = (response.json().get("user", {}).get("app_metadata") or {}).get("role")
    except (ValueError, AttributeError):
        app_role = None
    if not row or app_role != "admin":
        raise HTTPException(403, "This Supabase account is not linked to an FOM admin.")
    return LineLoginResponse(access_token=create_access_token(str(row["user_id"]), role="admin"), user=_public_user(row))
