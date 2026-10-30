"""Catalog Service."""
from urllib.parse import quote
from fastapi import Depends, HTTPException, Query
from app.schemas.auth import AuthUser
from app.schemas.domain import CategoryCreate, MenuCreate, MenuUpdate, OptionCreate, OptionGroupCreate, TagCreate
from app.services.auth_service import get_current_user
from app.services.data_api import delete_rows, get_one, insert_rows, patch_rows, select_rows
from app.services.common import owned_shop, require_role
async def list_categories():
    return await select_rows("categories", order="category_name.asc", limit=100)


async def create_category(payload: CategoryCreate, user: AuthUser = Depends(get_current_user)):
    shop = await owned_shop(payload.shop_id, user)
    body = payload.model_dump()
    rows = await insert_rows("categories", body)
    return rows[0] if rows else {}


async def update_category(category_id: int, payload: CategoryCreate, user: AuthUser = Depends(get_current_user)):
    category = await get_one("categories", {"category_id": f"eq.{category_id}"})
    if not category:
        raise HTTPException(404, "Category not found.")
    await owned_shop(category["shop_id"], user)
    body = payload.model_dump()
    if body["shop_id"] != category["shop_id"]:
        await owned_shop(body["shop_id"], user)
    rows = await patch_rows("categories", {"category_id": f"eq.{category_id}"}, body)
    if not rows:
        raise HTTPException(404, "Category not found.")
    return rows[0]


async def delete_category(category_id: int, user: AuthUser = Depends(get_current_user)):
    require_role(user, "admin")
    await delete_rows("categories", {"category_id": f"eq.{category_id}"})


async def list_menus(shop_id: int | None = None, category_id: int | None = None,
                     q: str | None = None, available_only: bool = True,
                     limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    filters: dict[str, str] = {"deleted_at": "is.null"}
    if shop_id is not None:
        filters["shop_id"] = f"eq.{shop_id}"
    if category_id is not None:
        filters["category_id"] = f"eq.{category_id}"
    if q:
        filters["menu_name"] = f"ilike.*{quote(q, safe='')}*"
    if available_only:
        filters["is_available"] = "eq.true"
    if shop_id is not None:
        shop = await get_one("shops", {"shop_id": f"eq.{shop_id}", "is_open": "eq.true"})
        if not shop:
            return {"items": [], "limit": limit, "offset": offset}
    else:
        open_shops = await select_rows("shops", select="shop_id", filters={"is_open": "eq.true"}, limit=100)
        ids = [str(s["shop_id"]) for s in open_shops]
        if not ids:
            return {"items": [], "limit": limit, "offset": offset}
        filters["shop_id"] = f"in.({','.join(ids)})"
    menus = await select_rows("menus", filters=filters, order="menu_name.asc", limit=limit, offset=offset)
    return {"items": menus, "limit": limit, "offset": offset}


async def create_menu(payload: MenuCreate, user: AuthUser = Depends(get_current_user)):
    require_role(user, "owner", "admin")
    await owned_shop(payload.shop_id, user)
    category = await get_one("categories", {"category_id": f"eq.{payload.category_id}", "shop_id": f"eq.{payload.shop_id}"})
    if not category:
        raise HTTPException(422, "Category must belong to the selected shop.")
    body = payload.model_dump(mode="json")
    rows = await insert_rows("menus", body)
    return rows[0] if rows else {}


async def get_menu(menu_id: int):
    menu = await get_one("menus", {"menu_id": f"eq.{menu_id}", "is_available": "eq.true", "deleted_at": "is.null"})
    if not menu:
        raise HTTPException(404, "Menu not found.")
    shop = await get_one("shops", {"shop_id": f"eq.{menu['shop_id']}", "is_open": "eq.true"})
    if not shop:
        raise HTTPException(404, "Menu not found.")
    return menu


async def update_menu(menu_id: int, payload: MenuUpdate, user: AuthUser = Depends(get_current_user)):
    menu = await get_one("menus", {"menu_id": f"eq.{menu_id}"})
    if not menu:
        raise HTTPException(404, "Menu not found.")
    await owned_shop(menu["shop_id"], user)
    rows = await patch_rows("menus", {"menu_id": f"eq.{menu_id}"}, payload.model_dump(exclude_unset=True, mode="json"))
    return rows[0] if rows else menu


async def delete_menu(menu_id: int, user: AuthUser = Depends(get_current_user)):
    menu = await get_one("menus", {"menu_id": f"eq.{menu_id}"})
    if not menu:
        raise HTTPException(404, "Menu not found.")
    await owned_shop(menu["shop_id"], user)
    # Soft-delete avoids breaking historical order references.
    await patch_rows("menus", {"menu_id": f"eq.{menu_id}"}, {"is_available": False})


async def list_menu_options(menu_id: int):
    menu = await get_one("menus", {"menu_id": f"eq.{menu_id}"})
    if not menu:
        raise HTTPException(404, "Menu not found.")
    groups = await select_rows("option_groups", filters={"menu_id": f"eq.{menu_id}"}, limit=100)
    result = []
    for group in groups:
        options = await select_rows("options", filters={"option_group_id": f"eq.{group['option_group_id']}", "is_available": "eq.true"}, limit=100)
        result.append({**group, "options": options})
    return result


async def create_option_group(menu_id: int, payload: OptionGroupCreate, user: AuthUser = Depends(get_current_user)):
    menu = await get_one("menus", {"menu_id": f"eq.{menu_id}"})
    if not menu:
        raise HTTPException(404, "Menu not found.")
    await owned_shop(menu["shop_id"], user)
    rows = await insert_rows("option_groups", {**payload.model_dump(), "menu_id": menu_id})
    return rows[0] if rows else {}


async def create_option(group_id: int, payload: OptionCreate, user: AuthUser = Depends(get_current_user)):
    group = await get_one("option_groups", {"option_group_id": f"eq.{group_id}"})
    if not group:
        raise HTTPException(404, "Option group not found.")
    menu = await get_one("menus", {"menu_id": f"eq.{group['menu_id']}"})
    await owned_shop(menu["shop_id"], user)
    rows = await insert_rows("options", {**payload.model_dump(mode="json"), "option_group_id": group_id})
    return rows[0] if rows else {}


async def list_tags(tag_type: str | None = None):
    filters = {"status": "eq.approved"}
    if tag_type:
        filters["tag_type"] = f"eq.{tag_type}"
    return await select_rows("tags", filters=filters, order="tag_name.asc", limit=200)


async def propose_tag(payload: TagCreate, user: AuthUser = Depends(get_current_user)):
    require_role(user, "owner", "admin")
    if payload.tag_type not in {"taste", "ingredient", "cooking_method"}:
        raise HTTPException(422, "Invalid tag type.")
    shop_id = None
    if user.role == "owner":
        shops = await select_rows("shops", filters={"owner_id": f"eq.{user.user_id}"}, limit=1)
        if not shops:
            raise HTTPException(403, "Create a shop before proposing tags.")
        shop_id = shops[0]["shop_id"]
    body = {**payload.model_dump(), "status": "approved" if user.role == "admin" else "pending", "requested_by_shop_id": shop_id}
    rows = await insert_rows("tags", body)
    return rows[0] if rows else {}


async def attach_tag_to_menu(menu_id: int, tag_id: int, user: AuthUser = Depends(get_current_user)):
    menu = await get_one("menus", {"menu_id": f"eq.{menu_id}"})
    if not menu:
        raise HTTPException(404, "Menu not found.")
    await owned_shop(menu["shop_id"], user)
    tag = await get_one("tags", {"tag_id": f"eq.{tag_id}", "status": "eq.approved"})
    if not tag:
        raise HTTPException(404, "Approved tag not found.")
    existing = await get_one("menu_tags", {"menu_id": f"eq.{menu_id}", "tag_id": f"eq.{tag_id}"})
    if existing:
        return existing
    rows = await insert_rows("menu_tags", {"menu_id": menu_id, "tag_id": tag_id})
    return rows[0] if rows else {"menu_id": menu_id, "tag_id": tag_id}


async def detach_tag_from_menu(menu_id: int, tag_id: int, user: AuthUser = Depends(get_current_user)):
    menu = await get_one("menus", {"menu_id": f"eq.{menu_id}"})
    if not menu:
        raise HTTPException(404, "Menu not found.")
    await owned_shop(menu["shop_id"], user)
    await delete_rows("menu_tags", {"menu_id": f"eq.{menu_id}", "tag_id": f"eq.{tag_id}"})

