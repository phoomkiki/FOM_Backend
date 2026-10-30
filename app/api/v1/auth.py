"""HTTP controllers for LINE and Supabase-admin authentication."""
from fastapi import APIRouter, Depends

from app.schemas.auth import AdminLoginRequest, AuthUser, LineLoginRequest, LineLoginResponse
from app.services.auth_service import get_current_user, login_with_line, login_admin

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/line", response_model=LineLoginResponse)
async def line_login(payload: LineLoginRequest) -> LineLoginResponse:
    """Verify a LINE ID token, then create or load the FOM user."""
    return await login_with_line(payload)


@router.post("/admin", response_model=LineLoginResponse)
async def admin_login(payload: AdminLoginRequest) -> LineLoginResponse:
    """Authenticate an admin through the authentication service."""
    return await login_admin(payload)


@router.get("/me", response_model=AuthUser)
async def get_me(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    return user


@router.post("/logout")
async def logout(user: AuthUser = Depends(get_current_user)) -> dict[str, str]:
    """FOM bearer tokens are stateless; client must delete the token."""
    return {"message": "Logged out. Discard the FOM access token on the client."}
