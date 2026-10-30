"""Payment Service."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fastapi import Depends, HTTPException
from app.schemas.auth import AuthUser
from app.schemas.domain import PaymentCreate, PaymentReview, SlipSubmit
from app.services.auth_service import get_current_user
from app.services.data_api import get_one, insert_rows, patch_rows, select_rows
from app.services.common import _promptpay_payload, owned_order, require_role
async def create_payment(payload: PaymentCreate, user: AuthUser = Depends(get_current_user)):
    order = await owned_order(payload.order_id, user)
    if order.get("status") != "pending_payment":
        raise HTTPException(409, "This order is not awaiting payment.")
    existing = await get_one("payments", {"order_id": f"eq.{payload.order_id}"})
    if existing:
        if existing.get("status") == "waiting_slip" and datetime.fromisoformat(existing["qr_expires_at"].replace("Z", "+00:00")) > datetime.now(timezone.utc):
            return {"payment": existing, "qr_payload": existing["qr_payload"], "amount": str(existing["amount"]), "expires_at": existing["qr_expires_at"]}
        raise HTTPException(409, "A payment record already exists for this order.")
    shop = await get_one("shops", {"shop_id": f"eq.{order['shop_id']}"})
    if not shop or not shop.get("promptpay_id"):
        raise HTTPException(422, "Shop has not configured a PromptPay ID.")
    amount = Decimal(str(order["total_amount"]))
    qr_payload = _promptpay_payload(str(shop["promptpay_id"]), amount)
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)
    rows = await insert_rows("payments", {
        "order_id": payload.order_id, "amount": str(amount), "qr_payload": qr_payload,
        "qr_expires_at": expires.isoformat(), "status": "waiting_slip",
    })
    if not rows:
        raise HTTPException(502, "Could not create payment.")
    return {"payment": rows[0], "qr_payload": qr_payload, "amount": str(amount), "expires_at": expires.isoformat(),
            "note": "QR creation does not confirm payment. Wait for transaction verification or admin review."}


async def submit_payment_slip(payment_id: int, payload: SlipSubmit, user: AuthUser = Depends(get_current_user)):
    payment = await get_one("payments", {"payment_id": f"eq.{payment_id}"})
    if not payment:
        raise HTTPException(404, "Payment not found.")
    await owned_order(payment["order_id"], user)
    if payment.get("status") != "waiting_slip":
        raise HTTPException(409, "This payment is no longer waiting for a slip.")
    if datetime.fromisoformat(payment["qr_expires_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
        await patch_rows("payments", {"payment_id": f"eq.{payment_id}"}, {"status": "expired"})
        raise HTTPException(410, "Payment QR has expired.")
    rows = await patch_rows("payments", {"payment_id": f"eq.{payment_id}", "status": "eq.waiting_slip"},
                            {"slip_image_url": payload.slip_image_url, "status": "manual_check"})
    if not rows:
        raise HTTPException(409, "Payment status changed; refresh and try again.")
    return rows[0]


async def my_payments(user: AuthUser = Depends(get_current_user)):
    orders = await select_rows("orders", filters={"user_id": f"eq.{user.user_id}"}, limit=100)
    ids = [str(o["order_id"]) for o in orders]
    if not ids:
        return []
    return await select_rows("payments", filters={"order_id": f"in.({','.join(ids)})"}, order="payment_id.desc", limit=100)


async def admin_payments(verify_status: str | None = None, user: AuthUser = Depends(get_current_user)):
    require_role(user, "admin")
    filters = {"status": f"eq.{verify_status}"} if verify_status else None
    return await select_rows("payments", filters=filters, order="payment_id.desc", limit=100)


async def admin_review_payment(payment_id: int, payload: PaymentReview, user: AuthUser = Depends(get_current_user)):
    require_role(user, "admin")
    if payload.verify_status not in {"passed", "failed"}:
        raise HTTPException(422, "verify_status must be passed or failed.")
    payment = await get_one("payments", {"payment_id": f"eq.{payment_id}"})
    if not payment:
        raise HTTPException(404, "Payment not found.")
    if payment.get("status") not in {"manual_check", "waiting_slip"}:
        raise HTTPException(409, "Payment has already been reviewed or is expired.")
    target_status = "manual_passed" if payload.verify_status == "passed" else "manual_failed"
    rows = await patch_rows("payments", {"payment_id": f"eq.{payment_id}", "status": f"in.(manual_check,waiting_slip)"},
                            {"status": target_status, "verified_at": datetime.now(timezone.utc).isoformat(), "reviewed_by": user.user_id})
    if not rows:
        raise HTTPException(409, "Payment was reviewed concurrently.")
    if payload.verify_status == "passed":
        now = datetime.now(timezone.utc).isoformat()
        await patch_rows("orders", {"order_id": f"eq.{payment['order_id']}", "status": "eq.pending_payment"},
                         {"status": "paid", "paid_at": now, "updated_at": now})
        await insert_rows("order_status_logs", {"order_id": payment["order_id"], "from_status": "pending_payment",
                          "to_status": "paid", "actor_type": "system", "actor_user_id": user.user_id})
    return rows[0]

