"""Recommendation Service: แนะนำเมนูในร้านให้ลูกค้าที่ล็อกอิน และบันทึก recommendation_logs

ข้อมูลทุกอย่างอ่านสดจากฐานข้อมูลทุกครั้งที่เรียก (ประวัติลูกค้า ยอดขายจาก view menu_sales เมนูและแท็ก)
ยอดขายจึงอัปเดตทันทีโดยไม่ต้องฝึกโมเดลใหม่ ส่วนค่า coef ของโมเดลมาจาก recommender_params.py
(สร้างโดย model/export_params.py)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.services import recommender as R
from app.services.data_api import get_one, insert_rows, patch_rows, select_rows

logger = logging.getLogger(__name__)

COUNTED_STATUSES = ("paid", "preparing", "ready", "delivering", "completed")
PAGE = 100  # data_api.select_rows จำกัดสูงสุด 100 แถวต่อครั้ง
MAX_ROWS = 5000
ATTRIBUTION_HOURS = 24  # นับว่า "สั่งตามที่แนะนำ" ถ้าสั่งภายในกี่ชั่วโมงหลังเห็นคำแนะนำ


def _load_params() -> dict | None:
    try:
        from app.services import recommender_params as P
    except ImportError:
        return None
    return {**P.PARAMS, "version": getattr(P, "MODEL_VERSION", "unknown")}


async def _select_all(table: str, *, select: str, order: str, filters: dict | None = None) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while offset < MAX_ROWS:
        batch = await select_rows(table, select=select, filters=filters, order=order, limit=PAGE, offset=offset)
        rows.extend(batch)
        if len(batch) < PAGE:
            return rows
        offset += PAGE
    logger.warning("recommendation: %s มีแถวเกิน %d ตัดที่เพดาน", table, MAX_ROWS)
    return rows


async def _candidate_menus(shop_id: int) -> list[dict]:
    return await _select_all(
        "menus",
        select="menu_id,menu_name,price,image_url,menu_tags(tag_id)",
        order="menu_id.asc",
        filters={"shop_id": f"eq.{shop_id}", "is_available": "eq.true", "deleted_at": "is.null"},
    )


async def _approved_tags() -> list[dict]:
    return await _select_all(
        "tags", select="tag_id,tag_type,status", order="tag_id.asc", filters={"status": "eq.approved"}
    )


async def _customer_orders(user_id: int) -> list[dict]:
    statuses = ",".join(COUNTED_STATUSES)
    return await _select_all(
        "orders",
        select="order_id,shop_id,order_items(menu_id)",
        order="created_at.asc,order_id.asc",
        filters={"user_id": f"eq.{user_id}", "status": f"in.({statuses})"},
    )


async def _sales(shop_id: int) -> dict[int, int]:
    try:
        rows = await _select_all(
            "menu_sales", select="menu_id,sales_count", order="menu_id.asc", filters={"shop_id": f"eq.{shop_id}"}
        )
    except HTTPException as exc:  # view ยังไม่ถูกสร้าง/ไม่มีสิทธิ์ ไม่ให้ทั้ง endpoint ล้ม
        logger.warning("recommendation: อ่าน menu_sales ไม่ได้ (%s) ใช้ยอดขาย 0 ทุกเมนู", exc.detail)
        return {}
    return {r["menu_id"]: int(r["sales_count"]) for r in rows}


async def _history_menus(menu_ids: list[int]) -> list[dict]:
    """เมนูที่ลูกค้าเคยสั่งในร้านอื่น (เอาเฉพาะที่ยังไม่ถูกลบ) ไว้สร้างโปรไฟล์"""
    out: list[dict] = []
    for start in range(0, len(menu_ids), PAGE):
        chunk = menu_ids[start:start + PAGE]
        out += await _select_all(
            "menus",
            select="menu_id,price,menu_tags(tag_id)",
            order="menu_id.asc",
            filters={"menu_id": f"in.({','.join(map(str, chunk))})", "deleted_at": "is.null"},
        )
    return out


async def _write_logs(user_id: int, shop_id: int, items: list[dict]) -> None:
    rows = [
        {"user_id": user_id, "shop_id": shop_id, "menu_id": it["menu_id"], "score": it["score"], "rank": it["rank"]}
        for it in items
    ]
    try:
        await insert_rows("recommendation_logs", rows)
    except HTTPException as exc:  # บันทึก log ไม่สำเร็จต้องไม่ทำให้คำแนะนำล้ม
        logger.warning("recommendation: บันทึก recommendation_logs ไม่สำเร็จ (%s)", exc.detail)


async def recommend(user_id: int, shop_id: int, limit: int = R.K, new_only: bool = False, *,
                    log: bool = True, params: dict | None = None) -> dict:
    params = params or _load_params()
    if params is None:
        raise HTTPException(503, "Recommendation model parameters have not been exported yet.")

    shop, candidates, tags, orders, sales = await asyncio.gather(
        get_one("shops", {"shop_id": f"eq.{shop_id}"}, select="shop_id"),
        _candidate_menus(shop_id),
        _approved_tags(),
        _customer_orders(user_id),
        _sales(shop_id),
    )
    if not shop:
        raise HTTPException(404, "Shop not found.")

    history = [
        [it["menu_id"] for it in (o.get("order_items") or []) if it.get("menu_id") is not None] for o in orders
    ]
    history = [h for h in history if h]
    candidate_ids = sorted({m["menu_id"] for m in candidates})
    extra_ids = sorted({i for h in history for i in h} - set(candidate_ids))
    menus = candidates + (await _history_menus(extra_ids) if extra_ids else [])
    tags_of_menu = {m["menu_id"]: {t["tag_id"] for t in (m.get("menu_tags") or [])} for m in menus}

    strategy, ranked = R.rank_for_customer(
        menus, tags_of_menu, R.build_vocab(tags), history, sales, candidate_ids, params, limit, new_only
    )
    by_id = {m["menu_id"]: m for m in candidates}
    items = [
        {
            "rank": rank,
            "menu_id": menu_id,
            "menu_name": by_id[menu_id]["menu_name"],
            "price": by_id[menu_id]["price"],
            "image_url": by_id[menu_id].get("image_url"),
            "score": round(score, 6),
        }
        for rank, (menu_id, score) in enumerate(ranked, 1)
    ]
    if log and items:
        await _write_logs(user_id, shop_id, items)
    return {
        "shop_id": shop_id,
        "strategy": strategy,
        "new_only": new_only,
        "model_version": params.get("version"),
        "items": items,
    }


async def mark_ordered(user_id: int, shop_id: int, menu_ids, order_id: int) -> int:
    """เรียกหลังสร้างออเดอร์: ทำเครื่องหมาย is_ordered ให้คำแนะนำที่ลูกค้าเห็นภายใน ATTRIBUTION_HOURS
    ชั่วโมงก่อนหน้า (ร้านเดียวกัน เมนูเดียวกัน) ไม่เคยทำให้การสร้างออเดอร์ล้ม คืนจำนวนแถวที่อัปเดต
    """
    ids = sorted({int(i) for i in menu_ids})
    if not ids:
        return 0
    since = (datetime.now(timezone.utc) - timedelta(hours=ATTRIBUTION_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        rows = await patch_rows(
            "recommendation_logs",
            {
                "user_id": f"eq.{user_id}",
                "shop_id": f"eq.{shop_id}",
                "menu_id": f"in.({','.join(map(str, ids))})",
                "is_ordered": "eq.false",
                "order_id": "is.null",
                "created_at": f"gte.{since}",
            },
            {"is_ordered": True, "order_id": order_id},
        )
    except Exception:  # noqa: BLE001 - ผลข้างเคียงแบบ best-effort ห้ามกระทบการสั่งซื้อ
        logger.exception("recommendation: mark_ordered ล้มเหลว (ข้ามไป)")
        return 0
    return len(rows)
