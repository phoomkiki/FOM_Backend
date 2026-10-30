"""Address Service."""
from fastapi import Depends, HTTPException
from app.schemas.auth import AuthUser
from app.schemas.domain import AddressCreate
from app.services.auth_service import get_current_user
from app.services.data_api import delete_rows, get_one, insert_rows, patch_rows, select_rows
async def list_addresses(user: AuthUser = Depends(get_current_user)):
    return await select_rows("addresses", filters={"user_id": f"eq.{user.user_id}"}, order="address_id.desc", limit=100)


async def create_address(payload: AddressCreate, user: AuthUser = Depends(get_current_user)):
    if payload.is_default:
        await patch_rows("addresses", {"user_id": f"eq.{user.user_id}"}, {"is_default": False})
    rows = await insert_rows("addresses", {**payload.model_dump(mode="json"), "user_id": user.user_id})
    return rows[0] if rows else {}


async def update_address(address_id: int, payload: AddressCreate, user: AuthUser = Depends(get_current_user)):
    address = await get_one("addresses", {"address_id": f"eq.{address_id}", "user_id": f"eq.{user.user_id}"})
    if not address:
        raise HTTPException(404, "Address not found.")
    body = payload.model_dump(exclude_unset=True, mode="json")
    if body.get("is_default"):
        await patch_rows("addresses", {"user_id": f"eq.{user.user_id}"}, {"is_default": False})
    rows = await patch_rows("addresses", {"address_id": f"eq.{address_id}", "user_id": f"eq.{user.user_id}"}, body)
    return rows[0] if rows else address


async def delete_address(address_id: int, user: AuthUser = Depends(get_current_user)):
    address = await get_one("addresses", {"address_id": f"eq.{address_id}", "user_id": f"eq.{user.user_id}"})
    if not address:
        raise HTTPException(404, "Address not found.")
    await delete_rows("addresses", {"address_id": f"eq.{address_id}", "user_id": f"eq.{user.user_id}"})

