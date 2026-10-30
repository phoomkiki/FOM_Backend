"""Profile-specific operations."""
from datetime import datetime, timezone
from fastapi import Depends, HTTPException
from app.schemas.auth import AuthUser
from app.schemas.domain import PdpaConsentUpdate, ProfileAddressUpdate, RefundAccountUpdate
from app.services.auth_service import get_current_user
from app.services.data_api import get_one, patch_rows


async def profile_me(user: AuthUser = Depends(get_current_user)):
    result = user.model_dump()
    address = await get_one("addresses", {"user_id": f"eq.{user.user_id}", "is_default": "eq.true"})
    result["phone"] = address.get("phone") if address else None
    result["refund_promptpay_id"] = None
    result["refund_account_name"] = None
    user_row = await get_one("users", {"user_id": f"eq.{user.user_id}"}, select="refund_promptpay_id,refund_account_name,pdpa_consent_at,pdpa_consent_version")
    if user_row:
        result.update(user_row)
        result["pdpa_consent"] = bool(user_row.get("pdpa_consent_at"))
    return result


async def update_refund_account(payload: RefundAccountUpdate, user: AuthUser = Depends(get_current_user)):
    body = payload.model_dump(exclude_unset=True)
    if not body:
        raise HTTPException(422, "Provide at least one refund account field to update.")
    rows = await patch_rows("users", {"user_id": f"eq.{user.user_id}"}, body)
    if not rows:
        raise HTTPException(404, "User not found.")
    return {"refund_promptpay_id": rows[0].get("refund_promptpay_id"), "refund_account_name": rows[0].get("refund_account_name")}


async def update_profile_address(address_id: int, payload: ProfileAddressUpdate, user: AuthUser = Depends(get_current_user)):
    address = await get_one("addresses", {"address_id": f"eq.{address_id}", "user_id": f"eq.{user.user_id}"})
    if not address:
        raise HTTPException(404, "Address not found.")
    body = payload.model_dump(exclude_unset=True, mode="json")
    if not body:
        raise HTTPException(422, "Provide at least one address field to update.")
    if body.get("is_default") is True:
        await patch_rows("addresses", {"user_id": f"eq.{user.user_id}"}, {"is_default": False})
    rows = await patch_rows("addresses", {"address_id": f"eq.{address_id}", "user_id": f"eq.{user.user_id}"}, body)
    return rows[0] if rows else address


async def update_pdpa_consent(payload: PdpaConsentUpdate, user: AuthUser = Depends(get_current_user)):
    rows = await patch_rows("users", {"user_id": f"eq.{user.user_id}"}, {
        "pdpa_consent_at": datetime.now(timezone.utc).isoformat(),
        "pdpa_consent_version": payload.pdpa_consent_version,
    })
    if not rows:
        raise HTTPException(404, "User not found.")
    return {"pdpa_consent": True, "pdpa_consent_version": rows[0].get("pdpa_consent_version"), "pdpa_consent_at": rows[0].get("pdpa_consent_at")}
