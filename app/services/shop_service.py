"""Shop Service."""
from urllib.parse import quote
from fastapi import Depends, HTTPException, Query
from app.schemas.auth import AuthUser
from app.schemas.domain import ShopCreate, ShopUpdate
from app.services.auth_service import get_current_user
from app.services.data_api import get_one, insert_rows, patch_rows, select_rows
from app.services.common import owned_shop, require_role
async def list_shops(q: str | None = None, category_id: int | None = None,
                     limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    filters = {"is_open": "eq.true"}
    if q:
        filters["shop_name"] = f"ilike.*{quote(q, safe='')}*"
    shops = await select_rows("shops", filters=filters, order="created_at.desc", limit=limit, offset=offset)
    if category_id is not None:
        menus = await select_rows("menus", filters={"category_id": f"eq.{category_id}", "is_available": "eq.true", "deleted_at": "is.null"}, limit=100)
        ids = {m["shop_id"] for m in menus}
        shops = [s for s in shops if s["shop_id"] in ids]
    return {"items": shops, "limit": limit, "offset": offset}


async def my_shops(user: AuthUser = Depends(get_current_user)):
    require_role(user, "owner", "admin")
    filters = {} if user.role == "admin" else {"owner_id": f"eq.{user.user_id}"}
    return await select_rows("shops", filters=filters, order="created_at.desc", limit=100)


async def create_shop(payload: ShopCreate, user: AuthUser = Depends(get_current_user)):
    require_role(user, "customer", "owner", "admin")
    body = payload.model_dump(mode="json")
    body.update({"owner_id": user.user_id, "is_open": False})
    rows = await insert_rows("shops", body)
    if not rows:
        raise HTTPException(502, "Shop was not created.")
    return rows[0]


async def get_shop(shop_id: int):
    shop = await get_one("shops", {"shop_id": f"eq.{shop_id}", "is_open": "eq.true"})
    if not shop:
        raise HTTPException(404, "Shop not found.")
    return shop


async def update_shop(shop_id: int, payload: ShopUpdate, user: AuthUser = Depends(get_current_user)):
    await owned_shop(shop_id, user)
    body = payload.model_dump(exclude_unset=True, mode="json")
    if not body:
        return await get_one("shops", {"shop_id": f"eq.{shop_id}"})
    rows = await patch_rows("shops", {"shop_id": f"eq.{shop_id}"}, body)
    return rows[0] if rows else await get_one("shops", {"shop_id": f"eq.{shop_id}"})


async def shop_orders(shop_id: int, status_filter: str | None = None,
                      limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                      user: AuthUser = Depends(get_current_user)):
    await owned_shop(shop_id, user)
    filters = {"shop_id": f"eq.{shop_id}"}
    if status_filter:
        filters["status"] = f"eq.{status_filter}"
    return {"items": await select_rows("orders", filters=filters, order="created_at.desc", limit=limit, offset=offset),
            "limit": limit, "offset": offset}


async def list_shop_hours(shop_id: int, user: AuthUser | None = None):
    shop = await get_one("shops", {"shop_id": f"eq.{shop_id}"})
    if not shop:
        raise HTTPException(404, "Shop not found.")
    return await select_rows("shop_hours", filters={"shop_id": f"eq.{shop_id}"}, order="weekday.asc", limit=7)


async def upsert_shop_hour(shop_id: int, payload, user: AuthUser = Depends(get_current_user)):
    await owned_shop(shop_id, user)
    if not payload.is_closed and (payload.open_time is None or payload.close_time is None):
        raise HTTPException(422, "open_time and close_time are required unless the shop is closed.")
    body = payload.model_dump(mode="json")
    body["shop_id"] = shop_id
    filters = {"shop_id": f"eq.{shop_id}", "weekday": f"eq.{payload.weekday}"}
    existing = await get_one("shop_hours", filters)
    if existing:
        rows = await patch_rows("shop_hours", filters, body)
    else:
        rows = await insert_rows("shop_hours", body)
    return rows[0] if rows else await get_one("shop_hours", filters)

