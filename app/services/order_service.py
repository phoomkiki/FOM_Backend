"""Order Service."""
from datetime import datetime, timezone
from decimal import Decimal
import secrets
from fastapi import Depends, HTTPException, Query
from app.schemas.auth import AuthUser
from app.schemas.domain import OrderCreate, OrderStatusUpdate
from app.services.auth_service import get_current_user
from app.services.data_api import get_one, insert_rows, patch_rows, select_rows
from app.services.common import owned_order
async def create_order(payload: OrderCreate, user: AuthUser = Depends(get_current_user)):
    address = await get_one("addresses", {"address_id": f"eq.{payload.address_id}", "user_id": f"eq.{user.user_id}"})
    if not address:
        raise HTTPException(422, "Choose one of your saved delivery addresses.")
    shop = await get_one("shops", {"shop_id": f"eq.{payload.shop_id}", "is_open": "eq.true"})
    if not shop:
        raise HTTPException(409, "This shop is not accepting orders.")
    menu_ids = list({item.menu_id for item in payload.items})
    menus = await select_rows("menus", filters={"menu_id": f"in.({','.join(map(str, menu_ids))})", "shop_id": f"eq.{payload.shop_id}", "is_available": "eq.true", "deleted_at": "is.null"}, limit=100)
    menu_map = {m["menu_id"]: m for m in menus}
    if len(menu_map) != len(menu_ids):
        raise HTTPException(422, "One or more menus are unavailable or belong to another shop.")
    food_total = Decimal("0")
    prepared = []
    for item in payload.items:
        menu = menu_map[item.menu_id]
        base_price = Decimal(str(menu["price"]))
        option_total = Decimal("0")
        selected_options = []
        groups = await select_rows("option_groups", filters={"menu_id": f"eq.{item.menu_id}"}, limit=100)
        group_map = {g["option_group_id"]: g for g in groups}
        opts = []
        if item.option_ids:
            unique_option_ids = set(item.option_ids)
            opts = await select_rows("options", filters={"option_id": f"in.({','.join(map(str, unique_option_ids))})", "is_available": "eq.true"}, limit=100)
            if len({o["option_id"] for o in opts}) != len(unique_option_ids):
                raise HTTPException(422, "One or more options are unavailable.")
        per_group: dict[int, int] = {}
        for opt in opts:
            group_id = opt["option_group_id"]
            if group_id not in group_map:
                raise HTTPException(422, "Selected option does not belong to this menu.")
            per_group[group_id] = per_group.get(group_id, 0) + 1
            option_total += Decimal(str(opt["extra_price"]))
            selected_options.append({"option_id": opt["option_id"], "option_name": opt["option_name"], "extra_price": str(opt["extra_price"])})
        for group in groups:
            count = per_group.get(group["option_group_id"], 0)
            if group.get("is_required") and count == 0:
                raise HTTPException(422, f"Please select an option for {group['group_name']}.")
            if count > int(group["max_select"]):
                raise HTTPException(422, f"Too many options selected for {group['group_name']}.")
        line_total = (base_price + option_total) * item.quantity
        food_total += line_total
        prepared.append((item, menu, base_price, line_total, selected_options))
    if food_total < Decimal(str(shop.get("min_order_amount") or 0)):
        raise HTTPException(422, "Order total does not meet this shop's minimum.")
    delivery_fee = Decimal(str(shop.get("delivery_fee") or 0))
    total_amount = food_total + delivery_fee
    order_rows = await insert_rows("orders", {
        "order_no": secrets.token_hex(5).upper(),
        "user_id": user.user_id, "shop_id": payload.shop_id, "address_id": payload.address_id,
        "delivery_label": address["label"], "delivery_phone": address["phone"],
        "delivery_address_text": address["address_text"], "delivery_landmark": address.get("landmark"),
        "delivery_latitude": address.get("latitude"), "delivery_longitude": address.get("longitude"),
        "food_total": str(food_total), "delivery_fee": str(delivery_fee), "total_amount": str(total_amount),
        "status": "pending_payment", "cancelled_by": None, "cancel_reason": None,
    })
    if not order_rows:
        raise HTTPException(502, "Could not create order.")
    order = order_rows[0]
    await insert_rows("order_status_logs", {
        "order_id": order["order_id"], "from_status": None, "to_status": "pending_payment",
        "actor_type": "customer", "actor_user_id": user.user_id, "reason": payload.note,
    })
    for item, menu, base_price, line_total, selected_options in prepared:
        item_rows = await insert_rows("order_items", {
            "order_id": order["order_id"], "menu_id": menu["menu_id"], "menu_name": menu["menu_name"],
            "quantity": item.quantity, "unit_price": str(base_price), "line_total": str(line_total), "note": item.note,
        })
        if item_rows:
            for opt in selected_options:
                await insert_rows("order_item_options", {
                    "order_item_id": item_rows[0]["order_item_id"], "option_id": opt["option_id"],
                    "option_name": opt["option_name"], "extra_price": opt["extra_price"],
                })
    return {**order, "items": [{"menu_id": m["menu_id"], "menu_name": m["menu_name"], "quantity": i.quantity,
                                 "unit_price": str(p), "line_total": str(t), "options": o}
                                for i, m, p, t, o in prepared]}


async def my_orders(status_filter: str | None = None, limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
                    user: AuthUser = Depends(get_current_user)):
    filters = {"user_id": f"eq.{user.user_id}"}
    if status_filter:
        filters["status"] = f"eq.{status_filter}"
    return {"items": await select_rows("orders", filters=filters, order="created_at.desc", limit=limit, offset=offset)}


async def get_order(order_id: int, user: AuthUser = Depends(get_current_user)):
    order = await owned_order(order_id, user)
    items = await select_rows("order_items", filters={"order_id": f"eq.{order_id}"}, limit=100)
    for item in items:
        item["options"] = await select_rows("order_item_options", filters={"order_item_id": f"eq.{item['order_item_id']}"}, limit=100)
    return {**order, "items": items}


async def update_order_status(order_id: int, payload: OrderStatusUpdate, user: AuthUser = Depends(get_current_user)):
    order = await get_one("orders", {"order_id": f"eq.{order_id}"})
    if not order:
        raise HTTPException(404, "Order not found.")
    shop = await get_one("shops", {"shop_id": f"eq.{order['shop_id']}"})
    if user.role != "admin" and user.user_id != order.get("user_id") and (not shop or user.user_id != shop.get("owner_id")):
        raise HTTPException(403, "You cannot update this order.")
    current, target = order["status"], payload.status
    if target == "cancelled" and order.get("batch_id") is not None:
        raise HTTPException(409, "This order is already assigned to a delivery batch.")
    allowed = {
        "pending_payment": {"cancelled"},
        "paid": {"preparing", "cancelled"},
        "preparing": {"ready"},
        "ready": {"cancelled"},
        "delivering": set(),
        "completed": set(),
        "cancelled": set(),
    }
    if target not in allowed.get(current, set()):
        raise HTTPException(409, f"Invalid order status transition: {current} -> {target}.")
    if target == "cancelled":
        if user.role != "admin" and user.user_id != order.get("user_id") and (not shop or user.user_id != shop.get("owner_id")):
            raise HTTPException(403, "Only the customer or shop owner can cancel this order.")
        actor = "customer" if user.user_id == order.get("user_id") else "shop"
        rows = await patch_rows("orders", {"order_id": f"eq.{order_id}", "status": f"eq.{current}"}, {
            "status": target, "cancelled_by": actor, "cancelled_at": datetime.now(timezone.utc).isoformat(),
            "cancel_reason": "Cancelled by user", "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    else:
        if target in {"preparing", "ready"} and user.role != "admin" and (not shop or user.user_id != shop.get("owner_id")):
            raise HTTPException(403, "Only the shop owner can update preparation status.")
        rows = await patch_rows("orders", {"order_id": f"eq.{order_id}", "status": f"eq.{current}"}, {
            "status": target, "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    if not rows:
        raise HTTPException(409, "Order status changed concurrently; refresh and try again.")
    await insert_rows("order_status_logs", {
        "order_id": order_id, "from_status": current, "to_status": target,
        "actor_type": "shop" if user.role == "owner" else ("system" if user.role == "admin" else "customer"),
        "actor_user_id": user.user_id,
    })
    return rows[0]

