"""ดึงข้อมูลจาก Supabase Data API (อ่านอย่างเดียว) แล้วพิมพ์รายงานตรวจข้อมูล

รันจากโฟลเดอร์รากของ repo backend (โฟลเดอร์ที่มีไฟล์ .env):
    python -m model.fetch_data                # ดึงข้อมูล + บันทึก model/data/snapshot.json + รายงาน
    python -m model.fetch_data --report-only  # อ่าน snapshot เดิม ไม่เรียก API

หมายเหตุ
- ใช้ SUPABASE_URL / SUPABASE_SECRET_KEY จาก .env ผ่าน app.core.config เหมือนตัว API
- ไม่ดึงตาราง users เก็บแค่ user_id ที่อยู่ในออเดอร์ (ไม่มีชื่อ/เบอร์/ที่อยู่ในไฟล์ที่เก็บ)
- สคริปต์นี้ไม่เขียนอะไรลงฐานข้อมูล และไม่พิมพ์ key ออกหน้าจอ
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).resolve().parent / "data"
SNAPSHOT = DATA_DIR / "snapshot.json"
PAGE_SIZE = 1000
COUNTED_STATUSES = ("paid", "preparing", "ready", "delivering", "completed")
TAG_TYPES = ("ingredient", "taste", "cooking_method")
PRICE_EDGES = (50, 70)  # <50 | 50-70 | >70  (เกณฑ์เดิมที่ตกลงกันไว้)
PRICE_LABELS = ("<50", "50-70", ">70")


def price_bucket(price: float) -> int:
    """0 = <50, 1 = 50-70 (รวมขอบ), 2 = >70"""
    if price < PRICE_EDGES[0]:
        return 0
    if price <= PRICE_EDGES[1]:
        return 1
    return 2


# ---------------------------------------------------------------------
# ดึงข้อมูล
# ---------------------------------------------------------------------
def _client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    # import ตรงนี้เพื่อให้ --report-only รันได้โดยไม่ต้องมี .env
    from app.core.config import settings
    from app.services.supabase_rest import _headers

    url = (settings.supabase_url or "").strip().rstrip("/")
    if url.endswith("/rest/v1"):
        url = url[:-8]
    key = (settings.supabase_service_role_key or "").strip()
    if not url or not key:
        sys.exit("ไม่พบ SUPABASE_URL / SUPABASE_SECRET_KEY ใน .env (ต้องรันจากโฟลเดอร์รากของ repo)")
    return httpx.Client(
        base_url=url + "/rest/v1", headers=_headers(key), timeout=30.0, transport=transport
    )


def _total(content_range: str | None) -> int | None:
    """Content-Range มีรูปแบบ '0-999/2043' หรือ '*/0'"""
    if not content_range or "/" not in content_range:
        return None
    tail = content_range.rsplit("/", 1)[1]
    return int(tail) if tail.isdigit() else None


def fetch_all(client: httpx.Client, table: str, select: str, order: str) -> list[dict]:
    """ดึงทุกแถวโดยแบ่งหน้า (PostgREST จำกัดจำนวนแถวต่อครั้ง) เรียงตามคีย์เพื่อให้หน้าไม่ซ้อนกัน"""
    rows: list[dict] = []
    offset = 0
    while True:
        resp = client.get(
            f"/{table}",
            params={"select": select, "order": order, "limit": str(PAGE_SIZE), "offset": str(offset)},
            headers={"Prefer": "count=exact"},
        )
        if resp.status_code >= 400:
            sys.exit(f"ดึงตาราง {table} ไม่สำเร็จ (HTTP {resp.status_code}): {resp.text[:300]}")
        batch = resp.json()
        rows.extend(batch)
        offset += len(batch)
        total = _total(resp.headers.get("content-range"))
        if not batch or (total is not None and offset >= total):
            break
    print(f"  ดึง {table:12s} {len(rows):>6d} แถว")
    return rows


def fetch_snapshot(transport: httpx.BaseTransport | None = None) -> dict:
    print("กำลังดึงข้อมูลจาก Supabase ...")
    with _client(transport) as c:
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "counted_statuses": list(COUNTED_STATUSES),
            "orders": fetch_all(c, "orders", "order_id,user_id,shop_id,status,created_at", "order_id"),
            "order_items": fetch_all(c, "order_items", "order_item_id,order_id,menu_id,quantity", "order_item_id"),
            "menus": fetch_all(
                c, "menus", "menu_id,shop_id,category_id,menu_name,price,is_available,deleted_at", "menu_id"
            ),
            "shops": fetch_all(c, "shops", "shop_id,shop_name,is_open", "shop_id"),
            "tags": fetch_all(c, "tags", "tag_id,tag_name,tag_type,status", "tag_id"),
            "menu_tags": fetch_all(c, "menu_tags", "menu_id,tag_id", "menu_id,tag_id"),
        }


# ---------------------------------------------------------------------
# รายงานตรวจข้อมูล
# ---------------------------------------------------------------------
def _dt(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def _dist(values: list) -> str:
    if not values:
        return "-"
    return f"min={min(values):g} / median={statistics.median(values):g} / max={max(values):g}"


def report(s: dict) -> None:
    warns: list[str] = []

    def head(title: str) -> None:
        print(f"\n=== {title} ===")

    counted_statuses = set(s.get("counted_statuses", COUNTED_STATUSES))
    orders = s["orders"]
    counted = [o for o in orders if o["status"] in counted_statuses]
    counted_ids = {o["order_id"] for o in counted}
    menus = {m["menu_id"]: m for m in s["menus"]}
    live = {i: m for i, m in menus.items() if not m["deleted_at"]}
    avail = {i: m for i, m in live.items() if m["is_available"]}

    print(f"snapshot ดึงเมื่อ {s.get('fetched_at', '?')}")

    head("1) จำนวนแถวที่ดึงมา")
    for k in ("orders", "order_items", "menus", "shops", "tags", "menu_tags"):
        print(f"  {k:12s} {len(s[k]):>6d}")

    head("2) สถานะออเดอร์")
    for st, n in Counter(o["status"] for o in orders).most_common():
        mark = "นับ" if st in counted_statuses else "ตัด"
        print(f"  {st:16s} {n:>6d}  [{mark}]")
    print(f"  ออเดอร์ที่ใช้ฝึก/ประเมิน: {len(counted)}")

    head("3) ช่วงเวลาของออเดอร์ที่นับ (ใช้เรียงลำดับก่อน-หลัง)")
    dts = [d for d in (_dt(o["created_at"]) for o in counted) if d]
    if dts:
        span = (max(dts) - min(dts)).total_seconds() / 86400
        distinct = len({o["created_at"] for o in counted})
        print(f"  ตั้งแต่ {min(dts):%Y-%m-%d %H:%M} ถึง {max(dts):%Y-%m-%d %H:%M} (กว้าง {span:.1f} วัน)")
        print(f"  ค่า created_at ที่ไม่ซ้ำกัน {distinct} ค่า จาก {len(counted)} ออเดอร์")
        times_by_user: dict[int, list[str]] = defaultdict(list)
        for o in counted:
            times_by_user[o["user_id"]].append(o["created_at"])
        multi = [v for v in times_by_user.values() if len(v) >= 2]
        tied = sum(1 for v in multi if len(set(v)) == 1)
        print(f"  ลูกค้าที่ทุกออเดอร์มีเวลาเดียวกันเป๊ะ: {tied} จาก {len(multi)} คน")
        if distinct < 0.5 * len(counted) or span < 1:
            warns.append("เวลาของออเดอร์ซ้ำกันมากหรืออยู่ในช่วงสั้นมาก (อาจ seed รวดเดียว) การแบ่งตามลำดับเวลาอาจไม่มีความหมาย")
        if multi and tied / len(multi) > 0.3:
            warns.append("ลูกค้าหลายคนมีทุกออเดอร์เวลาเดียวกัน ลำดับก่อน-หลังของคนเหล่านั้นไม่น่าเชื่อถือ")
    else:
        warns.append("อ่านเวลา created_at ของออเดอร์ไม่ได้เลย")

    head("4) ลูกค้า")
    per_user = Counter(o["user_id"] for o in counted)
    n_orders = list(per_user.values())
    print(f"  ลูกค้าที่มีออเดอร์ {len(per_user)} คน | ออเดอร์ต่อคน {_dist(n_orders)}")
    for lim in (3, 6, 10):
        print(f"  น้อยกว่า {lim:>2d} ออเดอร์: {sum(1 for n in n_orders if n < lim)} คน")
    if n_orders and statistics.median(n_orders) < 5:
        warns.append("ลูกค้ามีออเดอร์ต่อคนน้อย (median < 5) ประวัติสั้นเกินไปสำหรับสร้างโปรไฟล์และแบ่ง train/valid/test")

    head("5) รายการในออเดอร์")
    items_by_order: dict[int, list[dict]] = defaultdict(list)
    for it in s["order_items"]:
        if it["order_id"] in counted_ids:
            items_by_order[it["order_id"]].append(it)
    all_items = [it for v in items_by_order.values() for it in v]
    null_menu = sum(1 for it in all_items if it["menu_id"] is None)
    qty_gt1 = sum(1 for it in all_items if (it.get("quantity") or 1) > 1)
    distinct_n = Counter(
        min(len({it["menu_id"] for it in v if it["menu_id"] is not None}), 4) for v in items_by_order.values()
    )
    dup = sum(1 for v in items_by_order.values() if len(v) != len({it["menu_id"] for it in v}))
    print(f"  ออเดอร์ที่ไม่มีรายการเลย: {len(counted_ids - set(items_by_order))}")
    print("  จำนวนเมนูไม่ซ้ำต่อออเดอร์: " + ", ".join(f"{k}{'+' if k == 4 else ''} เมนู={distinct_n[k]}" for k in (1, 2, 3, 4)))
    print(f"  รายการที่ menu_id เป็น NULL: {null_menu} จาก {len(all_items)}")
    print(f"  รายการที่ quantity > 1: {qty_gt1} (ตอนฝึกนับเป็นสั่งเมนูนั้น 1 ครั้ง)")
    print(f"  ออเดอร์ที่มีเมนูเดียวกันซ้ำหลายแถว: {dup}")
    if all_items and null_menu / len(all_items) > 0.05:
        warns.append("รายการที่ menu_id เป็น NULL เกิน 5% ข้อมูลประวัติสูญเสียมาก")

    head("6) ร้านและเมนู")
    shops = {sh["shop_id"]: sh for sh in s["shops"]}
    orders_by_shop = Counter(o["shop_id"] for o in counted)
    avail_by_shop = Counter(m["shop_id"] for m in avail.values())
    print(f"  {'shop_id':>7s}  {'เมนูสั่งได้':>10s}  {'ออเดอร์':>7s}  ชื่อร้าน")
    small = []
    for sid in sorted(shops):
        n_menu = avail_by_shop.get(sid, 0)
        if n_menu <= 5:
            small.append(sid)
        print(f"  {sid:>7d}  {n_menu:>10d}  {orders_by_shop.get(sid, 0):>7d}  {str(shops[sid]['shop_name'])[:30]}")
    if small:
        print(f"  ร้านที่มีเมนูสั่งได้ไม่เกิน 5 เมนู: {small} (แนะนำครบทุกเมนูก็ได้ Hit@5 = 100% จะข้ามตอนประเมิน)")
    order_menu_ids = {it["menu_id"] for it in all_items if it["menu_id"] is not None}
    print(f"  เมนูทั้งหมด {len(menus)} | ถูกลบ(soft delete) {len(menus) - len(live)} | ปิดขาย {len(live) - len(avail)}")
    print(f"  menu_id ในออเดอร์ที่ไม่มีในตาราง menus: {len(order_menu_ids - set(menus))}")
    print(f"  menu_id ในออเดอร์ที่เมนูถูกลบไปแล้ว: {len(order_menu_ids & (set(menus) - set(live)))}")

    head("7) แท็ก")
    tags = {t["tag_id"]: t for t in s["tags"]}
    print("  สถานะแท็ก: " + ", ".join(f"{k}={v}" for k, v in Counter(t["status"] for t in tags.values()).items()))
    approved = {i: t for i, t in tags.items() if t["status"] == "approved"}
    by_type = Counter(t["tag_type"] for t in approved.values())
    unknown = [k for k in by_type if k not in TAG_TYPES]
    if unknown:
        warns.append(f"พบ tag_type ที่ไม่อยู่ใน {TAG_TYPES}: {unknown}")
    tags_of_menu: dict[int, set[int]] = defaultdict(set)
    stale = unapproved = orphan = 0
    for r in s["menu_tags"]:
        m, t = menus.get(r["menu_id"]), tags.get(r["tag_id"])
        if m is None:
            orphan += 1
        elif m["deleted_at"]:
            stale += 1
        elif t is None or t["status"] != "approved":
            unapproved += 1
        else:
            tags_of_menu[r["menu_id"]].add(r["tag_id"])
    for tt in TAG_TYPES:
        counts = [
            sum(1 for tid in tags_of_menu.get(mid, ()) if approved[tid]["tag_type"] == tt) for mid in live
        ]
        none = sum(1 for c in counts if c == 0)
        mean = statistics.mean(counts) if counts else 0
        print(f"  {tt:15s} แท็ก {by_type[tt]:>3d} | เมนูที่มีแท็กชนิดนี้ {len(live) - none}/{len(live)} | เฉลี่ย {mean:.2f} แท็ก/เมนู")
        if live and none / len(live) > 0.3:
            warns.append(f"เมนูเกิน 30% ไม่มีแท็กชนิด {tt}")
    print(f"  menu_tags ที่ชี้เมนูที่ถูกลบ: {stale} | ชี้แท็กที่ยังไม่อนุมัติ: {unapproved} | ชี้เมนูที่ไม่มี: {orphan} (ตัดทิ้งตอนฝึก)")

    head("8) ราคาเมนู (เมนูที่ยังไม่ถูกลบ)")
    prices = [float(m["price"]) for m in live.values()]
    print(f"  ราคา {_dist(prices)}")
    buckets = Counter(price_bucket(p) for p in prices)
    print("  ช่วงราคา: " + ", ".join(f"{PRICE_LABELS[i]}={buckets[i]}" for i in range(3)))
    in_orders = Counter(
        price_bucket(float(menus[it["menu_id"]]["price"])) for it in all_items if it["menu_id"] in menus
    )
    print("  ช่วงราคาของรายการที่ถูกสั่ง: " + ", ".join(f"{PRICE_LABELS[i]}={in_orders[i]}" for i in range(3)))

    head("สรุปข้อควรระวัง")
    if warns:
        for w in warns:
            print(f"  [เตือน] {w}")
    else:
        print("  ไม่พบจุดที่น่ากังวลจากการตรวจเบื้องต้น")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # กันภาษาไทยเพี้ยนเวลา redirect ลงไฟล์
    ap = argparse.ArgumentParser(description="ดึงข้อมูลจาก Supabase และพิมพ์รายงานตรวจข้อมูล")
    ap.add_argument("--report-only", action="store_true", help="อ่าน snapshot เดิม ไม่เรียก API")
    args = ap.parse_args()

    if args.report_only:
        if not SNAPSHOT.exists():
            sys.exit(f"ไม่พบ {SNAPSHOT} ให้รันโดยไม่ใส่ --report-only ก่อน")
        snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    else:
        snap = fetch_snapshot()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
        print(f"บันทึกแล้ว: {SNAPSHOT}")
    report(snap)


if __name__ == "__main__":
    main()
