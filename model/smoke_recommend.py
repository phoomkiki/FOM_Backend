"""ลองเรียกระบบแนะนำกับฐานข้อมูลจริงโดยไม่ต้องล็อกอิน LINE (ใช้ service key จาก .env) ไม่บันทึก log

รัน (จากโฟลเดอร์รากของ repo backend):
    python -m model.smoke_recommend --user 12 --shop 1
    python -m model.smoke_recommend --user 12 --shop 1 --new-only --limit 10
ใช้ตรวจว่า query ไป Supabase ทำงานถูกต้อง (view menu_sales, การดึงแท็ก/ประวัติ) ก่อนเปิดให้ front เรียก
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

from fastapi import HTTPException

from app.services import recommendation_service as S


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="ลองเรียกระบบแนะนำกับฐานข้อมูลจริง (ไม่บันทึก log)")
    ap.add_argument("--user", type=int, required=True, help="users.user_id")
    ap.add_argument("--shop", type=int, required=True, help="shops.shop_id")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--new-only", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    try:
        out = asyncio.run(S.recommend(args.user, args.shop, args.limit, args.new_only, log=False))
    except HTTPException as exc:
        sys.exit(f"ล้มเหลว: HTTP {exc.status_code} {exc.detail}")
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print(f"\nใช้เวลา {time.time() - t0:.2f} วินาที")


if __name__ == "__main__":
    main()
