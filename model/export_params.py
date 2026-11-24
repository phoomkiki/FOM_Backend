"""ส่งออกค่าโมเดลที่ฝึกแล้ว (จาก model/data/train_result.json) เป็นไฟล์ Python ที่ API ใช้งาน

รัน (จากโฟลเดอร์รากของ repo backend หลัง python -m model.train):
    python -m model.export_params                  # ใช้ "LR ทุกเมนู" (lr_all)
    python -m model.export_params --model lr_new   # ใช้ "LR เมนูใหม่"

ผลลัพธ์: app/services/recommender_params.py  (commit ไฟล์นี้ขึ้น git เพื่อให้ Vercel เห็น)
เป็นไฟล์ .py ไม่ใช่ JSON เพราะ Vercel รวมเฉพาะไฟล์ Python เข้า bundle อย่างแน่นอน
ค่าที่ส่งออกมีแค่ coef ของฟีเจอร์ 6 ตัว + intercept + half_life ไม่มีข้อมูลลูกค้า
ยอดขาย ประวัติลูกค้า และรายชื่อแท็กอ่านสดจากฐานข้อมูลทุกครั้งที่เรียก API
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.services import recommender as R

ROOT = Path(__file__).resolve().parents[1]
RESULT = Path(__file__).resolve().parent / "data" / "train_result.json"
OUT = ROOT / "app" / "services" / "recommender_params.py"
LABEL = {"lr_all": "LR ทุกเมนู", "lr_new": "LR เมนูใหม่"}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="ส่งออกค่าโมเดลที่ฝึกแล้วให้ API")
    ap.add_argument("--model", choices=sorted(LABEL), default="lr_all")
    args = ap.parse_args()
    if not RESULT.exists():
        sys.exit(f"ไม่พบ {RESULT} ให้รัน python -m model.train ก่อน")

    res = json.loads(RESULT.read_text(encoding="utf-8"))
    m = res["tuned"][args.model]
    if list(m["feature_names"]) != list(R.FEATURE_NAMES):
        sys.exit(
            "ลำดับฟีเจอร์ของโมเดลไม่ตรงกับ recommender.FEATURE_NAMES (ฝึกกับโค้ดคนละเวอร์ชัน) "
            "ให้รัน python -m model.train ใหม่"
        )
    if len(m["coef"]) != len(R.FEATURE_NAMES):
        sys.exit("จำนวน coef ไม่ถูกต้อง")

    fetched = res.get("snapshot_fetched_at") or "unknown"
    version = f"{args.model}-{fetched[:10]}"
    params = {
        "name": args.model,
        "half_life": m["half_life"],
        "feature_names": list(m["feature_names"]),
        "coef": m["coef"],
        "intercept": m["intercept"],
    }
    evidence = {
        "valid_hit": m["valid_hit"],
        "C": m["C"],
        "test": {mode: res["metrics"][mode].get(LABEL[args.model]) for mode in ("all", "new_only")},
        "counts": res.get("counts"),
    }
    body = (
        '"""สร้างโดย model/export_params.py ห้ามแก้ด้วยมือ (รัน python -m model.export_params ใหม่แทน)"""\n'
        f"MODEL_VERSION = {version!r}\n"
        f"TRAINED_ON_SNAPSHOT = {fetched!r}\n"
        f"EXPORTED_AT = {datetime.now(timezone.utc).isoformat(timespec='seconds')!r}\n"
        f"PARAMS = {json.dumps(params, ensure_ascii=False, indent=4)}\n"
        f"EVIDENCE = {json.dumps(evidence, ensure_ascii=False, indent=4)}\n"
    )
    OUT.write_text(body, encoding="utf-8")
    print(f"เขียนแล้ว: {OUT}")
    print(f"โมเดล {LABEL[args.model]} | เวอร์ชัน {version} | half_life={m['half_life']} C={m['C']}")
    print("coef: " + ", ".join(f"{n}={w:+.3f}" for n, w in zip(R.FEATURE_NAMES, m["coef"])))
    print("อย่าลืม git add app/services/recommender_params.py")


if __name__ == "__main__":
    main()
