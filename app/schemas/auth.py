from pydantic import BaseModel, Field


class LineLoginRequest(BaseModel):
    id_token: str = Field(min_length=20, max_length=10000)


class AdminLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class AuthUser(BaseModel):
    """Public user profile. Role is not a field on the FOM users table or user payload."""
    user_id: int
    line_user_id: str | None = None
    display_name: str
    img_url: str | None = None
    phone: str | None = None
    account_status: str = "active"
    created_at: str | None = None


class AuthPrincipal(AuthUser):
    """Internal authenticated identity with authorization context, not public user data."""
    role: str


class LineLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUser
