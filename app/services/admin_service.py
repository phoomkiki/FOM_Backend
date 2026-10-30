"""Admin Service."""
from datetime import datetime, timezone
from fastapi import Depends, HTTPException, Query
from app.schemas.auth import AuthUser
from app.schemas.domain import AdminRoleUpdate, ShopApproval, TagReview
from app.services.auth_service import get_current_user
from app.services.data_api import get_one, patch_rows, select_rows
from app.services.supabase_rest import get_user_by_id
from app.services.common import VALID_ROLES, require_role
async def admin_overview(user: AuthUser = Depends(get_current_user)):
    require_role(user, "admin")
    result = {}
    for table in ("users", "shops", "orders", "payments", "deliveries"):
        rows = await select_rows(table, select="*", limit=100)
        result[table] = {"sample": rows, "returned": len(rows), "note": "Limited to latest/first 100 rows; use list endpoints for paging."}
    return result


async def admin_users(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                      user: AuthUser = Depends(get_current_user)):
    require_role(user, "admin")
    return {"items": await select_rows("users", order="created_at.desc", limit=limit, offset=offset), "limit": limit, "offset": offset}


async def admin_update_role(user_id: int, payload: AdminRoleUpdate, user: AuthUser = Depends(get_current_user)):
    require_role(user, "admin")
    if payload.role not in VALID_ROLES:
        raise HTTPException(422, "Role must be customer, owner, or admin.")
    target = await get_user_by_id(user_id)
    if not target:
        raise HTTPException(404, "User not found.")
    # Roles are not stored in public.users: admin comes from Supabase Auth app_metadata,
    # and owner is derived from shops.owner_id. Never write a non-existent users.role column.
    if payload.role == "owner":
        shops = await select_rows("shops", filters={"owner_id": f"eq.{user_id}"}, limit=1)
        if not shops:
            raise HTTPException(409, "A user becomes an owner by creating a shop; role cannot be assigned in users.")
        return {"user": target, "role": "owner", "message": "Owner role is derived from shops.owner_id."}
    raise HTTPException(409, "Roles are not stored in public.users. Manage admin in Supabase Auth app_metadata; customer/owner roles are derived from shop ownership.")


async def admin_shops(user: AuthUser = Depends(get_current_user)):
    require_role(user, "admin")
    return await select_rows("shops", order="created_at.desc", limit=100)


async def admin_shop_approval(shop_id: int, payload: ShopApproval, user: AuthUser = Depends(get_current_user)):
    require_role(user, "admin")
    # The current database has no approval_status/approved_by/approved_at columns.
    # Do not pretend an approval decision was persisted in a different field.
    shop = await get_one("shops", {"shop_id": f"eq.{shop_id}"})
    if not shop:
        raise HTTPException(404, "Shop not found.")
    raise HTTPException(409, "The current database has no shop approval fields. This endpoint is disabled until the schema supports shop moderation.")


async def admin_orders(status_filter: str | None = None, limit: int = Query(50, ge=1, le=100),
                       offset: int = Query(0, ge=0), user: AuthUser = Depends(get_current_user)):
    require_role(user, "admin")
    filters = {"status": f"eq.{status_filter}"} if status_filter else None
    return {"items": await select_rows("orders", filters=filters, order="created_at.desc", limit=limit, offset=offset),
            "limit": limit, "offset": offset}


async def admin_tags(status_filter: str | None = None, user: AuthUser = Depends(get_current_user)):
    require_role(user, "admin")
    filters = {"status": f"eq.{status_filter}"} if status_filter else None
    return await select_rows("tags", filters=filters, order="created_at.desc", limit=200)


async def admin_review_tag(tag_id: int, payload: TagReview, user: AuthUser = Depends(get_current_user)):
    require_role(user, "admin")
    if payload.status not in {"approved", "rejected", "pending"}:
        raise HTTPException(422, "Invalid tag status.")
    rows = await patch_rows("tags", {"tag_id": f"eq.{tag_id}"},
                            {"status": payload.status, "reviewed_at": datetime.now(timezone.utc).isoformat(),
                             "reject_reason": payload.reject_reason})
    if not rows:
        raise HTTPException(404, "Tag not found.")
    return rows[0]

