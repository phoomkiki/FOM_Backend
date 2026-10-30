"""Shared authorization and payment helpers for domain services."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import secrets
from urllib.parse import quote
from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from app.core.config import settings
from app.core.security import ALGORITHM
from app.schemas.auth import AuthUser
from app.schemas.domain import (
    AddressCreate, AdminRoleUpdate, CategoryCreate, DeliveryBatchCreate,
    DeliveryClaim, DeliveryComplete, MenuCreate, MenuUpdate, OptionCreate,
    OptionGroupCreate, OrderCreate, OrderStatusUpdate, PaymentCreate,
    PaymentReview, ShopApproval, ShopCreate, ShopUpdate,
    SlipSubmit, TagCreate, TagReview,
)
from app.services.auth_service import get_current_user
from app.services.data_api import (
    delete_rows, get_one, insert_rows, patch_rows, select_rows,
)
from app.services.supabase_rest import get_user_by_id

ALLOWED_ORDER_TRANSITIONS = {
    "pending_payment": {"paid", "cancelled"},
    "paid": {"preparing", "cancelled"},
    "preparing": {"ready"},
    "ready": {"delivering", "cancelled"},
    "delivering": {"completed"},
    "completed": set(),
    "cancelled": set(),
}


VALID_ROLES = {"customer", "owner", "admin"}


def require_role(user: AuthUser, *roles: str) -> None:
    if user.role not in roles:
        raise HTTPException(status_code=403, detail="You do not have permission to perform this action.")


async def owned_shop(shop_id: int, user: AuthUser) -> dict:
    shop = await get_one("shops", {"shop_id": f"eq.{shop_id}"})
    if not shop:
        raise HTTPException(404, "Shop not found.")
    if user.role != "admin" and shop.get("owner_id") != user.user_id:
        raise HTTPException(403, "You do not own this shop.")
    return shop


async def owned_order(order_id: int, user: AuthUser) -> dict:
    order = await get_one("orders", {"order_id": f"eq.{order_id}"})
    if not order:
        raise HTTPException(404, "Order not found.")
    if user.role not in {"admin"} and order.get("user_id") != user.user_id:
        shop = await get_one("shops", {"shop_id": f"eq.{order.get('shop_id')}"}, "shop_id,owner_id")
        if not shop or shop.get("owner_id") != user.user_id:
            raise HTTPException(403, "You cannot access this order.")
    return order


def _promptpay_payload(promptpay_id: str, amount: Decimal) -> str:
    """Build a PromptPay EMVCo payload for Thai mobile numbers or 13-digit IDs."""
    digits = "".join(ch for ch in promptpay_id if ch.isdigit())
    if len(digits) == 10 and digits.startswith("0"):
        target = "0066" + digits[1:]
        subtag = "01"
    elif len(digits) == 13:
        target = digits
        subtag = "02"
    else:
        raise HTTPException(422, "Shop PromptPay ID must be a 10-digit Thai mobile number or 13-digit national/merchant ID.")

    def tlv(tag: str, value: str) -> str:
        return f"{tag}{len(value):02d}{value}"

    merchant = tlv("00", "A000000677010111") + tlv(subtag, target)
    payload = (
        tlv("00", "01") + tlv("01", "12") + tlv("29", merchant)
        + tlv("53", "764") + tlv("54", f"{amount:.2f}") + tlv("58", "TH")
        + "6304"
    )
    crc = 0xFFFF
    for byte in payload.encode("ascii"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return payload + f"{crc:04X}"


