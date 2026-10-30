"""Delivery Service."""
from datetime import datetime, timedelta, timezone
import secrets
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from app.core.config import settings
from app.core.security import ALGORITHM
from app.schemas.auth import AuthUser
from app.schemas.domain import DeliveryBatchCreate, DeliveryClaim, DeliveryComplete
from app.services.auth_service import get_current_user
from app.services.data_api import get_one, insert_rows, patch_rows, select_rows
from app.services.common import owned_shop, require_role
async def create_delivery_batch(payload: DeliveryBatchCreate, user: AuthUser = Depends(get_current_user)):
    require_role(user, "owner", "admin")
    orders = []
    for oid in set(payload.order_ids):
        order = await get_one("orders", {"order_id": f"eq.{oid}"})
        if not order:
            raise HTTPException(404, f"Order {oid} not found.")
        await owned_shop(order["shop_id"], user)
        if order.get("status") != "ready":
            raise HTTPException(409, f"Order {oid} is not ready for delivery.")
        if order.get("batch_id") is not None:
            existing_batch = await get_one("delivery_batches", {"batch_id": f"eq.{order['batch_id']}"})
            if existing_batch and existing_batch.get("status") == "active":
                raise HTTPException(409, f"Order {oid} is already in an active delivery batch.")
        if orders and order["shop_id"] != orders[0]["shop_id"]:
            raise HTTPException(422, "A delivery batch can only contain orders from one shop.")
        orders.append(order)
    if not orders:
        raise HTTPException(422, "Select at least one order.")
    batch_code = secrets.token_hex(5).upper()
    expires = datetime.now(timezone.utc) + timedelta(minutes=payload.expires_in_minutes)
    raw_token = jwt.encode({"batch_code": batch_code, "token_type": "delivery_qr", "exp": expires},
                           settings.secret_key, algorithm=ALGORITHM)
    batch_rows = await insert_rows("delivery_batches", {
        "shop_id": orders[0]["shop_id"], "batch_code": batch_code, "qr_token": raw_token, "status": "active",
    })
    if not batch_rows:
        raise HTTPException(502, "Could not create delivery batch.")
    batch = batch_rows[0]
    for order in orders:
        await patch_rows("orders", {"order_id": f"eq.{order['order_id']}", "status": "eq.ready"},
                         {"batch_id": batch["batch_id"]})
    return {"batch_id": batch["batch_id"], "token": raw_token, "expires_at": expires.isoformat(),
            "orders": [{"order_id": o["order_id"], "total_amount": o["total_amount"]} for o in orders],
            "warning": "Show the QR only to the intended rider; it expires and cannot be retrieved again."}


async def scan_delivery_batch(token: str):
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        if claims.get("token_type") != "delivery_qr":
            raise JWTError("wrong token type")
        batch_code = claims.get("batch_code")
    except JWTError as exc:
        raise HTTPException(410, "Delivery QR is invalid or expired.") from exc
    batch = await get_one("delivery_batches", {"batch_code": f"eq.{batch_code}"})
    if not batch or batch.get("qr_token") != token or batch.get("status") != "active":
        raise HTTPException(404, "Delivery QR is invalid or no longer available.")
    orders = await select_rows("orders", filters={"batch_id": f"eq.{batch['batch_id']}"}, order="order_id.asc", limit=100)
    return {"batch_id": batch["batch_id"], "status": batch["status"], "scanned_at": batch.get("scanned_at"),
            "orders": [{"order_id": o["order_id"], "status": o["status"], "delivery_address": {
                "label": o["delivery_label"], "phone": o["delivery_phone"], "address_text": o["delivery_address_text"],
                "landmark": o.get("delivery_landmark"), "latitude": o.get("delivery_latitude"), "longitude": o.get("delivery_longitude")
            }} for o in orders]}


async def claim_delivery_batch(token: str, payload: DeliveryClaim):
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        if claims.get("token_type") != "delivery_qr":
            raise JWTError("wrong token type")
        batch_code = claims.get("batch_code")
    except JWTError as exc:
        raise HTTPException(410, "Delivery QR is invalid or expired.") from exc
    batch = await get_one("delivery_batches", {"batch_code": f"eq.{batch_code}"})
    if not batch or batch.get("qr_token") != token or batch.get("status") != "active":
        raise HTTPException(409, "This delivery batch is not available.")
    rows = await patch_rows("delivery_batches", {"batch_id": f"eq.{batch['batch_id']}", "status": "eq.active", "scanned_at": "is.null"},
                            {"scanned_at": datetime.now(timezone.utc).isoformat()})
    if not rows:
        raise HTTPException(409, "Another rider has already claimed this batch.")
    orders = await select_rows("orders", filters={"batch_id": f"eq.{batch['batch_id']}", "status": "eq.ready"}, limit=100)
    for order in orders:
        await patch_rows("orders", {"order_id": f"eq.{order['order_id']}", "status": "eq.ready"},
                         {"status": "delivering", "updated_at": datetime.now(timezone.utc).isoformat()})
        await insert_rows("order_status_logs", {"order_id": order["order_id"], "from_status": "ready",
                          "to_status": "delivering", "actor_type": "rider", "batch_id": batch["batch_id"]})
    session_expiry = datetime.now(timezone.utc) + timedelta(minutes=180)
    rider_token = jwt.encode({"sub": f"guest-rider:{batch['batch_id']}", "batch_id": batch["batch_id"],
                              "rider_name": payload.name, "rider_phone": payload.phone,
                              "token_type": "guest_rider", "exp": session_expiry},
                             settings.secret_key, algorithm=ALGORITHM)
    return {"batch_id": batch["batch_id"], "status": "active", "rider_token": rider_token,
            "expires_at": session_expiry.isoformat(),
            "message": "Batch claimed. Use rider_token to confirm each delivery separately."}


async def complete_delivery(order_id: int, payload: DeliveryComplete,
                            credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        claims = jwt.decode(credentials.credentials, settings.secret_key, algorithms=[ALGORITHM])
        if claims.get("token_type") != "guest_rider":
            raise JWTError("not a guest rider token")
        rider_batch_id = int(claims.get("batch_id"))
    except (JWTError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(401, "A valid guest-rider token is required.") from exc
    order = await get_one("orders", {"order_id": f"eq.{order_id}"})
    if not order:
        raise HTTPException(404, "Order not found.")
    if order.get("status") == "completed":
        raise HTTPException(409, "This order is already completed.")
    if order.get("status") != "delivering":
        raise HTTPException(409, "Only orders currently being delivered can be completed.")
    if int(order.get("batch_id") or 0) != rider_batch_id:
        raise HTTPException(403, "This rider token does not belong to this order's batch.")
    batch = await get_one("delivery_batches", {"batch_id": f"eq.{rider_batch_id}"})
    if not batch or batch.get("status") != "active" or batch.get("scanned_at") is None:
        raise HTTPException(409, "Delivery batch has not been claimed.")
    existing = await get_one("deliveries", {"order_id": f"eq.{order_id}"})
    if existing:
        raise HTTPException(409, "Proof for this delivery has already been submitted.")
    now = datetime.now(timezone.utc).isoformat()
    rows = await insert_rows("deliveries", {
        "order_id": order_id, "batch_id": rider_batch_id, "proof_image_url": payload.proof_image_url,
        "proof_taken_at": now, "proof_time_source": "upload", "delivery_note": payload.delivery_note,
    })
    if not rows:
        raise HTTPException(502, "Could not save delivery proof.")
    updated = await patch_rows("orders", {"order_id": f"eq.{order_id}", "status": "eq.delivering"},
                               {"status": "completed", "completed_at": now, "updated_at": now})
    if not updated:
        raise HTTPException(409, "Order status changed before delivery completion.")
    await insert_rows("order_status_logs", {"order_id": order_id, "from_status": "delivering", "to_status": "completed",
                      "actor_type": "rider", "batch_id": rider_batch_id})
    remaining = await select_rows("orders", filters={"batch_id": f"eq.{rider_batch_id}", "status": "neq.completed"}, limit=100)
    if not remaining:
        await patch_rows("delivery_batches", {"batch_id": f"eq.{rider_batch_id}", "status": "eq.active"},
                         {"status": "completed", "completed_at": now})
    return {"delivery": rows[0], "order": updated[0], "remaining_deliveries": len(remaining)}


async def admin_deliveries(user: AuthUser = Depends(get_current_user)):
    require_role(user, "admin")
    return await select_rows("deliveries", order="created_at.desc", limit=100)


async def admin_delivery_batches(user: AuthUser = Depends(get_current_user)):
    require_role(user, "admin")
    return await select_rows("delivery_batches", order="created_at.desc", limit=100)


async def admin_revoke_batch(batch_id: int, user: AuthUser = Depends(get_current_user)):
    require_role(user, "admin")
    rows = await patch_rows("delivery_batches", {"batch_id": f"eq.{batch_id}", "status": "eq.active"},
                            {"status": "cancelled", "cancelled_at": datetime.now(timezone.utc).isoformat()})
    if not rows:
        raise HTTPException(404, "Active delivery batch not found.")
    return rows[0]

