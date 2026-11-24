"""ทดสอบ recommendation_service ด้วยฐานข้อมูลจำลองในหน่วยความจำ (ไม่ยิง Supabase จริง)

หมายเหตุ: ฐานข้อมูลจำลองตรวจ "ตรรกะ" ของ service เท่านั้น ไม่ได้ตรวจ syntax ของ PostgREST
(เช่น embedded select) ให้ใช้ python -m model.smoke_recommend ตรวจกับ Supabase จริงอีกครั้ง
"""
import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.services import recommendation_service as rs

PARAMS = {"half_life": 0, "coef": [2, 0, 0, 0, 0, 0], "intercept": 0.5, "version": "test"}


def menu(menu_id, shop_id, price=40, available=True, deleted=None):
    return {"menu_id": menu_id, "shop_id": shop_id, "menu_name": f"m{menu_id}", "price": price,
            "image_url": None, "is_available": available, "deleted_at": deleted}


def tables():
    return {
        "shops": [{"shop_id": 1}, {"shop_id": 2}],
        "menus": [
            menu(1, 1), menu(2, 1), menu(3, 1, price=80),
            menu(4, 1, available=False),               # ปิดขาย ต้องไม่ถูกแนะนำ
            menu(5, 1, deleted="2026-01-01T00:00:00Z"),  # ถูกลบ ต้องไม่ถูกแนะนำ
            menu(20, 2),                                # ร้านอื่น
        ],
        "tags": [
            {"tag_id": 1, "tag_type": "ingredient", "status": "approved"},
            {"tag_id": 2, "tag_type": "ingredient", "status": "approved"},
            {"tag_id": 3, "tag_type": "taste", "status": "approved"},
            {"tag_id": 4, "tag_type": "ingredient", "status": "pending"},
        ],
        "menu_tags": [
            {"menu_id": 1, "tag_id": 1}, {"menu_id": 1, "tag_id": 3}, {"menu_id": 2, "tag_id": 2},
            {"menu_id": 3, "tag_id": 1}, {"menu_id": 4, "tag_id": 1}, {"menu_id": 5, "tag_id": 1},
            {"menu_id": 20, "tag_id": 1},
        ],
        "menu_sales": [
            {"menu_id": 1, "shop_id": 1, "sales_count": 10},
            {"menu_id": 2, "shop_id": 1, "sales_count": 50},
            {"menu_id": 3, "shop_id": 1, "sales_count": 30},
        ],
        "orders": [
            {"order_id": 100, "user_id": 10, "shop_id": 2, "status": "completed", "created_at": "2026-10-01T10:00:00Z"},
            {"order_id": 101, "user_id": 12, "shop_id": 1, "status": "cancelled", "created_at": "2026-10-01T10:00:00Z"},
            {"order_id": 102, "user_id": 12, "shop_id": 1, "status": "pending_payment", "created_at": "2026-10-02T10:00:00Z"},
            {"order_id": 103, "user_id": 13, "shop_id": 1, "status": "paid", "created_at": "2026-10-03T10:00:00Z"},
        ],
        "order_items": [
            {"order_id": 100, "menu_id": 20}, {"order_id": 101, "menu_id": 2}, {"order_id": 102, "menu_id": 2},
            {"order_id": 103, "menu_id": 1}, {"order_id": 103, "menu_id": 3},
        ],
    }


class FakeDB:
    def __init__(self, tbl, fail_insert=False):
        self.t, self.inserted, self.fail_insert = tbl, [], fail_insert

    async def select_rows(self, table, *, select="*", filters=None, order=None, limit=100, offset=0):
        rows = [dict(r) for r in self.t[table]]
        for col, cond in (filters or {}).items():
            op, _, val = cond.partition(".")
            if op == "eq":
                rows = [r for r in rows if str(r[col]).lower() == val.lower()]
            elif op == "in":
                allowed = set(val.strip("()").split(","))
                rows = [r for r in rows if str(r[col]) in allowed]
            elif op == "is" and val == "null":
                rows = [r for r in rows if r[col] is None]
            else:
                raise AssertionError(f"ฐานข้อมูลจำลองไม่รองรับตัวกรอง {col}={cond}")
        if order:
            keys = [o.split(".")[0] for o in order.split(",")]
            rows.sort(key=lambda r: tuple(r[k] for k in keys))
        if "menu_tags(" in select:
            for r in rows:
                r["menu_tags"] = [{"tag_id": x["tag_id"]} for x in self.t["menu_tags"] if x["menu_id"] == r["menu_id"]]
        if "order_items(" in select:
            for r in rows:
                r["order_items"] = [{"menu_id": x["menu_id"]} for x in self.t["order_items"] if x["order_id"] == r["order_id"]]
        return rows[offset:offset + limit]

    async def get_one(self, table, filters, select="*"):
        rows = await self.select_rows(table, filters=filters, limit=1)
        return rows[0] if rows else None

    async def insert_rows(self, table, rows):
        if self.fail_insert:
            raise HTTPException(502, "Supabase rejected the server-side database request.")
        self.inserted.append((table, rows))
        return rows


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB(tables())
    monkeypatch.setattr(rs, "select_rows", fake.select_rows)
    monkeypatch.setattr(rs, "get_one", fake.get_one)
    monkeypatch.setattr(rs, "insert_rows", fake.insert_rows)
    return fake


def run(user_id, shop_id=1, **kw):
    return asyncio.run(rs.recommend(user_id, shop_id, params=PARAMS, **kw))


def ids(result):
    return [it["menu_id"] for it in result["items"]]


def test_personalized_uses_history_from_other_shops(db):
    # ผู้ใช้ 10 เคยสั่งเมนู 20 (ร้าน 2, วัตถุดิบ 1) -> ร้าน 1 แนะนำเมนูวัตถุดิบ 1 ก่อน
    out = run(10)
    assert out["strategy"] == "personalized" and out["model_version"] == "test"
    assert ids(out) == [1, 3, 2]
    assert [it["rank"] for it in out["items"]] == [1, 2, 3]


def test_unavailable_deleted_and_other_shop_menus_are_never_recommended(db):
    assert set(ids(run(10, limit=20))) == {1, 2, 3}


def test_cold_start_uses_live_sales(db):
    out = run(11)
    assert out["strategy"] == "popular_fallback"
    assert ids(out) == [2, 3, 1]  # ยอดขาย 50, 30, 10


def test_cancelled_and_unpaid_orders_do_not_count_as_history(db):
    assert run(12)["strategy"] == "popular_fallback"


def test_sales_update_is_reflected_immediately(db):
    db.t["menu_sales"][0]["sales_count"] = 999  # เมนู 1 ขายได้เพิ่ม
    assert ids(run(11)) == [1, 2, 3]


def test_new_only_excludes_menus_the_user_already_ordered(db):
    assert ids(run(13, new_only=True)) == [2]


def test_limit_is_respected(db):
    assert len(run(10, limit=2)["items"]) == 2


def test_recommendations_are_logged_with_rank_and_score(db):
    out = run(10)
    (table, rows), = db.inserted
    assert table == "recommendation_logs"
    assert [(r["menu_id"], r["rank"]) for r in rows] == [(it["menu_id"], it["rank"]) for it in out["items"]]
    assert all(r["user_id"] == 10 and r["shop_id"] == 1 and "score" in r for r in rows)


def test_log_false_writes_nothing(db):
    run(10, log=False)
    assert db.inserted == []


def test_log_failure_does_not_break_the_response(monkeypatch):
    fake = FakeDB(tables(), fail_insert=True)
    monkeypatch.setattr(rs, "select_rows", fake.select_rows)
    monkeypatch.setattr(rs, "get_one", fake.get_one)
    monkeypatch.setattr(rs, "insert_rows", fake.insert_rows)
    assert ids(run(10)) == [1, 3, 2]


def test_missing_sales_view_degrades_gracefully(monkeypatch, db):
    original = db.select_rows

    async def no_view(table, **kw):
        if table == "menu_sales":
            raise HTTPException(404, "Resource not found in menu_sales.")
        return await original(table, **kw)

    monkeypatch.setattr(rs, "select_rows", no_view)
    assert ids(run(10)) == [1, 3, 2]


def test_unknown_shop_is_404(db):
    with pytest.raises(HTTPException) as exc:
        run(10, shop_id=999)
    assert exc.value.status_code == 404


def test_missing_model_params_is_503(monkeypatch, db):
    monkeypatch.setattr(rs, "_load_params", lambda: None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(rs.recommend(10, 1))
    assert exc.value.status_code == 503


def test_select_all_follows_pagination(monkeypatch):
    data = [{"menu_id": i} for i in range(250)]

    async def fake(table, *, select, filters, order, limit, offset):
        return data[offset:offset + limit]

    monkeypatch.setattr(rs, "select_rows", fake)
    assert len(asyncio.run(rs._select_all("menus", select="menu_id", order="menu_id.asc"))) == 250


def test_mark_ordered_patches_only_recent_unmarked_logs(monkeypatch):
    calls = []

    async def fake_patch(table, filters, body):
        calls.append((table, filters, body))
        return [{"log_id": 1}, {"log_id": 2}]

    monkeypatch.setattr(rs, "patch_rows", fake_patch)
    assert asyncio.run(rs.mark_ordered(10, 1, [3, 1, 3], 555)) == 2
    table, filters, body = calls[0]
    assert table == "recommendation_logs" and body == {"is_ordered": True, "order_id": 555}
    assert filters["user_id"] == "eq.10" and filters["shop_id"] == "eq.1"
    assert filters["menu_id"] == "in.(1,3)"
    assert filters["is_ordered"] == "eq.false" and filters["order_id"] == "is.null"
    assert filters["created_at"].startswith("gte.20") and filters["created_at"].endswith("Z")


def test_mark_ordered_never_raises(monkeypatch):
    async def boom(table, filters, body):
        raise HTTPException(502, "down")

    monkeypatch.setattr(rs, "patch_rows", boom)
    assert asyncio.run(rs.mark_ordered(10, 1, [1], 555)) == 0
    assert asyncio.run(rs.mark_ordered(10, 1, [], 555)) == 0


def test_recommendations_endpoint_requires_authentication():
    from app.main import app
    assert TestClient(app).get("/api/v1/shops/1/recommendations").status_code == 401


def test_openapi_lists_recommendations_endpoint():
    from app.main import app
    paths = app.openapi()["paths"]
    assert "get" in paths["/api/v1/shops/{shop_id}/recommendations"]
