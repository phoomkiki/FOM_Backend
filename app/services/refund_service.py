"""Refund Service."""
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import Depends, HTTPException
from app.schemas.auth import AuthUser
from app.services.auth_service import get_current_user
from app.services.data_api import get_one, insert_rows, patch_rows, select_rows
from app.services.common import require_role
async def create_refund(order_id: int, payload, user: AuthUser = Depends(get_current_user)):
    order = await get_one("orders", {"order_id": f"eq.{order_id}"})
    if not order:
        raise HTTPException(404, "Order not found.")
    if order.get("user_id") != user.user_id and user.role != "admin":
        raise HTTPException(403, "Only the customer who placed this order can request a refund.")
    if order.get("status") not in {"cancelled", "paid", "preparing", "ready", "completed"}:
        raise HTTPException(409, "This order is not eligible for a refund request.")
    if payload.amount > Decimal(str(order["total_amount"])):
        raise HTTPException(422, "Refund amount cannot exceed the order total.")
    existing = await get_one("refunds", {"order_id": f"eq.{order_id}"})
    if existing:
        raise HTTPException(409, "A refund record already exists for this order.")
    user_row = await get_one("users", {"user_id": f"eq.{user.user_id}"})
    promptpay_id = payload.refund_promptpay_id or (user_row or {}).get("refund_promptpay_id")
    account_name = payload.refund_account_name or (user_row or {}).get("refund_account_name")
    if not promptpay_id:
        raise HTTPException(422, "Provide a refund PromptPay ID or save one in your profile.")
    rows = await insert_rows("refunds", {
        "order_id": order_id, "amount": str(payload.amount), "promptpay_id": promptpay_id,
        "account_name": account_name, "status": "pending",
    })
    if not rows:
        raise HTTPException(502, "Could not create refund request.")
    await insert_rows("activity_logs", {
        "actor_type": "customer", "actor_user_id": user.user_id, "shop_id": order["shop_id"],
        "action": "refund_requested", "entity_type": "refund", "entity_id": rows[0]["refund_id"],
        "new_data": {"reason": payload.reason, "status": "pending"},
    })
    return {**rows[0], "reason": payload.reason}


async def my_refunds(user: AuthUser = Depends(get_current_user)):
    orders = await select_rows("orders", select="order_id", filters={"user_id": f"eq.{user.user_id}"}, limit=100)
    ids = [str(o["order_id"]) for o in orders]
    if not ids:
        return []
    return await select_rows("refunds", filters={"order_id": f"in.({','.join(ids)})"}, order="created_at.desc", limit=100)


async def admin_refunds(status_filter: str | None = None, user: AuthUser = Depends(get_current_user)):
    require_role(user, "admin")
    filters = {"status": f"eq.{status_filter}"} if status_filter else None
    return await select_rows("refunds", filters=filters, order="created_at.desc", limit=100)


async def admin_review_refund(refund_id: int, payload, user: AuthUser = Depends(get_current_user)):
    require_role(user, "admin")
    if payload.status != "refunded":
        raise HTTPException(422, "The current database supports only pending -> refunded for refunds.")
    refund = await get_one("refunds", {"refund_id": f"eq.{refund_id}"})
    if not refund:
        raise HTTPException(404, "Refund request not found.")
    if refund["status"] != "pending":
        raise HTTPException(409, "Refund has already been processed.")
    now = datetime.now(timezone.utc).isoformat()
    rows = await patch_rows("refunds", {"refund_id": f"eq.{refund_id}", "status": "eq.pending"},
                            {"status": "refunded", "refunded_by": user.user_id, "refunded_at": now})
    if not rows:
        raise HTTPException(409, "Refund request changed concurrently.")
    await insert_rows("activity_logs", {
        "actor_type": "system", "actor_user_id": user.user_id,
        "action": "refund_processed", "entity_type": "refund", "entity_id": refund_id,
        "old_data": {"status": "pending"},
        "new_data": {"status": "refunded", "admin_note": payload.admin_note},
    })
    return rows[0]

