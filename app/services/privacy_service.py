"""Privacy Service."""
from datetime import datetime, timezone
from fastapi import Depends, HTTPException
from app.schemas.auth import AuthUser
from app.services.auth_service import get_current_user
from app.services.data_api import get_one, insert_rows, patch_rows, select_rows
from app.services.common import require_role
async def create_privacy_request(payload, user: AuthUser = Depends(get_current_user)):
    if payload.request_type not in {"access", "export", "correct", "delete"}:
        raise HTTPException(422, "Unsupported privacy request type.")
    existing = await get_one("privacy_requests", {"user_id": f"eq.{user.user_id}", "status": "eq.pending"})
    if existing:
        raise HTTPException(409, "You already have an active privacy request.")
    reason = f"[{payload.request_type}] {payload.reason or ''}".strip()
    rows = await insert_rows("privacy_requests", {"user_id": user.user_id, "status": "pending", "reason": reason})
    if not rows:
        raise HTTPException(502, "Could not create privacy request.")
    return rows[0]


async def my_privacy_requests(user: AuthUser = Depends(get_current_user)):
    return await select_rows("privacy_requests", filters={"user_id": f"eq.{user.user_id}"}, order="created_at.desc", limit=100)


async def admin_privacy_requests(status_filter: str | None = None, user: AuthUser = Depends(get_current_user)):
    require_role(user, "admin")
    filters = {"status": f"eq.{status_filter}"} if status_filter else None
    return await select_rows("privacy_requests", filters=filters, order="created_at.desc", limit=100)


async def admin_review_privacy_request(request_id: int, payload, user: AuthUser = Depends(get_current_user)):
    require_role(user, "admin")
    if payload.status not in {"completed", "rejected"}:
        raise HTTPException(422, "The current database supports pending -> completed/rejected.")
    row = await get_one("privacy_requests", {"request_id": f"eq.{request_id}"})
    if not row:
        raise HTTPException(404, "Privacy request not found.")
    if row["status"] != "pending":
        raise HTTPException(409, "Privacy request is already closed.")
    reason = row.get("reason") or ""
    if payload.reason:
        reason = (reason + "\nAdmin: " + payload.reason).strip()
    rows = await patch_rows("privacy_requests", {"request_id": f"eq.{request_id}", "status": "eq.pending"},
                            {"status": payload.status, "reason": reason,
                             "completed_at": datetime.now(timezone.utc).isoformat() if payload.status == "completed" else None})
    if not rows:
        raise HTTPException(409, "Privacy request changed concurrently.")
    return rows[0]
