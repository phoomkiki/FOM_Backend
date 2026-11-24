"""ฝึก/จูน/เทียบวิธีแนะนำเมนูบนข้อมูลจริงจาก snapshot (ได้จาก model.fetch_data)

รัน (จากโฟลเดอร์รากของ repo backend):
    pip install -r model/requirements.txt          # ครั้งแรกครั้งเดียว
    python -m model.fetch_data                     # ดึงข้อมูลล่าสุด
    python -m model.train                          # ใช้ค่าเริ่มต้น (Optuna 150 รอบ)
    python -m model.train --trials 300 --no-grid

โครงเหมือน train_model.py / tune_model.py เดิม (ตัวชี้วัดหลักคือ Hit@5) ที่ต่างไปมีเท่านี้
  - ข้อมูลมาจาก snapshot แทนข้อมูลสุ่ม รายชื่อแท็กสร้างจากตาราง tags ที่อนุมัติแล้ว
  - ตัดรายการของเมนูที่ถูกลบ (soft delete) ออกจากประวัติ/เป้าหมาย ส่วนเมนูที่ปิดขายชั่วคราว
    ยังเป็นผู้สมัครตอนประเมิน (ตอนที่ถูกสั่งมันยังขายอยู่) แต่ตอนให้บริการจริงจะถูกกรองออก
  - ข้ามออเดอร์ที่มีเมนูผู้สมัครไม่เกิน 5 เมนู (แนะนำครบทุกเมนูก็ Hit = 100% จึงไม่บอกอะไร)
  - เพิ่ม MRR, NDCG@5, ช่วงความเชื่อมั่น 95% (bootstrap รายลูกค้า) และผลต่างเทียบ "เมนูขายดี"
  - grid เดิมมีตัวแปร wc ที่ไม่ถูกใช้ (รันซ้ำผลเหมือนกัน 3 เท่า) ที่นี่ตัดทิ้ง ผลลัพธ์ไม่เปลี่ยน
  - half-life นับเป็นจำนวนออเดอร์ เหมือนเดิม
ผลทั้งหมดถูกบันทึกที่ model/data/train_result.json เพื่อใช้ในขั้น export
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from itertools import product
from pathlib import Path

import numpy as np
import optuna
from sklearn.linear_model import LogisticRegression

from app.services import recommender as R

DATA_DIR = Path(__file__).resolve().parent / "data"
SNAPSHOT = DATA_DIR / "snapshot.json"
RESULT = DATA_DIR / "train_result.json"

SEED = 50
N_TRIALS = 150
RANDOM_REPEATS = 20
BOOTSTRAP = 1000
METRICS = ("HitRate@5", "Precision@5", "Recall@5", "MRR", "NDCG@5")
METHODS = [
    "สุ่ม",
    "เมนูขายดี",
    "เคยสั่งบ่อย+ขายดี",
    "Filter แท็กโปรด",
    "CBF พื้นฐาน",
    "CBF ปรับน้ำหนัก (Grid)",
    "CBF ปรับน้ำหนัก (Optuna)",
    "LR ทุกเมนู",
    "LR เมนูใหม่",
]


# ---------------------------------------------------------------------
# ข้อมูล
# ---------------------------------------------------------------------
def _ts(value: str):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return datetime.min


class Dataset:
    """แปลง snapshot เป็นเมทริกซ์เมนู + ออเดอร์ (ลูกค้า, ลำดับ, ร้าน, แถวเมนู) เรียงตามเวลา"""

    def __init__(self, snap: dict):
        counted = set(snap.get("counted_statuses", []))
        menus = sorted((m for m in snap["menus"] if not m["deleted_at"]), key=lambda m: m["menu_id"])
        self.menus = menus
        self.row = {m["menu_id"]: r for r, m in enumerate(menus)}
        self.shop_of = np.array([m["shop_id"] for m in menus])
        self.shop_rows = {int(s): np.where(self.shop_of == s)[0] for s in np.unique(self.shop_of)}

        self.vocab = R.build_vocab(snap["tags"])
        approved = {t["tag_id"] for t in snap["tags"] if t["status"] == "approved"}
        tags_of_menu: dict[int, set[int]] = defaultdict(set)
        for r in snap["menu_tags"]:
            if r["tag_id"] in approved:
                tags_of_menu[r["menu_id"]].add(r["tag_id"])
        self.X = R.menu_matrix(menus, tags_of_menu, self.vocab)
        self.slices, self.dim = R.group_slices(self.vocab)

        items_of: dict[int, set[int]] = defaultdict(set)
        for it in snap["order_items"]:
            if it["menu_id"] in self.row:
                items_of[it["order_id"]].add(self.row[it["menu_id"]])
        by_c: dict[int, list] = defaultdict(list)
        self.n_orders_counted = 0
        self.n_orders_dropped = 0
        for o in snap["orders"]:
            if o["status"] not in counted:
                continue
            self.n_orders_counted += 1
            rows = {r for r in items_of.get(o["order_id"], ()) if self.shop_of[r] == o["shop_id"]}
            if not rows:
                self.n_orders_dropped += 1
                continue
            by_c[o["user_id"]].append((_ts(o["created_at"]), o["order_id"], o["shop_id"], tuple(sorted(rows))))
        self.orders: list[tuple] = []  # (ลูกค้า, ลำดับของลูกค้า, ร้าน, แถวเมนู)
        for c, lst in by_c.items():
            lst.sort(key=lambda x: (x[0], x[1]))
            for t, (_, _, shop, items) in enumerate(lst):
                self.orders.append((c, t, shop, items))


def split(orders):
    """แบ่งรายลูกค้าตามเวลา: ~80% แรก = train+valid, ที่เหลือ = test (วิธีเดียวกับสคริปต์เดิม)"""
    by_c = defaultdict(list)
    for o in orders:
        by_c[o[0]].append(o)
    train, valid, test = [], [], []
    for _, os_ in by_c.items():
        os_.sort(key=lambda o: o[1])
        cut = int(len(os_) * 0.8)
        vcut = max(1, cut - max(1, len(os_) // 10))
        train += os_[:vcut]
        valid += os_[vcut:cut]
        test += os_[cut:]
    return train, valid, test


def orders_by_customer(orders):
    d = defaultdict(list)
    for c, t, s, items in sorted(orders, key=lambda o: (o[0], o[1])):
        d[c].append((s, items))
    return d


def build_states(orders, X, half_life):
    return {
        c: R.customer_state([items for _, items in oc], X, half_life)
        for c, oc in orders_by_customer(orders).items()
    }


def sales_vector(orders, n_menus):
    v = np.zeros(n_menus)
    for _, _, _, items in orders:
        for i in items:
            v[i] += 1
    return v


def seen_of(states):
    return {c: st[2] for c, st in states.items() if st}


# ---------------------------------------------------------------------
# ตัวเรียงลำดับ: rank(ลูกค้า, ผู้สมัคร) -> แถวเมนูเรียงจากดีไปแย่
# ---------------------------------------------------------------------
def make_random(seed=1):
    rng = np.random.default_rng(seed)
    return lambda c, cand: rng.permutation(cand)


def make_popular(sales):
    return lambda c, cand: cand[R.order_popular(sales[cand])]


def make_repeat_popular(states, sales):
    def rank(c, cand):
        st = states.get(c)
        raw = st[2] if st else {}
        mine = np.array([raw.get(i, 0) for i in cand], dtype=float)
        return cand[R.order_repeat_popular(mine, sales[cand])]

    return rank


def make_favorite(ds, states, sales):
    def rank(c, cand):
        st = states.get(c)
        if st is None:
            return cand[R.order_popular(sales[cand])]
        return cand[R.order_favorite_tag(st[0], ds.X[cand], sales[cand], ds.slices["ingredient"])]

    return rank


def make_cbf_basic(ds, states, sales):
    def rank(c, cand):
        st = states.get(c)
        if st is None:
            return cand[R.order_popular(sales[cand])]
        return cand[R.order_cbf_basic(st[0], ds.X[cand])]

    return rank


def make_cbf_tuned(Xw, states, sales, params):
    def rank(c, cand):
        st = states.get(c)
        if st is None:
            return cand[R.order_popular(sales[cand])]
        prof, weighted, _ = st
        wc = np.array([weighted.get(i, 0.0) for i in cand])
        score = R.cbf_scores(prof, Xw[cand], wc, sales[cand], params["repeat"], params["pop"])
        return cand[R.order_by_score(score)]

    return rank


def make_lr(ds, states, sales, coef, intercept):
    def rank(c, cand):
        st = states.get(c)
        if st is None:
            return cand[R.order_popular(sales[cand])]
        prof, _, raw = st
        raw_c = np.array([raw.get(i, 0) for i in cand], dtype=float)
        F = R.lr_features(prof, raw_c, ds.X[cand], sales[cand], ds.slices)
        return cand[R.order_by_score(R.lr_scores(coef, intercept, F))]

    return rank


def cbf_ranker(ds, hist_orders, sales, weights, hl, params):
    Xw = R.apply_weights(ds.X, ds.vocab, weights)
    return make_cbf_tuned(Xw, build_states(hist_orders, Xw, hl), sales, params)


# ---------------------------------------------------------------------
# ประเมิน
# ---------------------------------------------------------------------
def order_metrics(ranked, target):
    k = R.K
    ranked = list(map(int, ranked))
    hits = sum(1 for i in ranked[:k] if i in target)
    rr = 0.0
    for pos, i in enumerate(ranked):
        if i in target:
            rr = 1.0 / (pos + 1)
            break
    dcg = sum(1.0 / np.log2(p + 2) for p, i in enumerate(ranked[:k]) if i in target)
    idcg = sum(1.0 / np.log2(p + 2) for p in range(min(len(target), k)))
    return [float(hits > 0), hits / k, hits / len(target), rr, dcg / idcg]


def evaluate(ds, rank, orders, seen, new_only=False, repeats=1, min_cand=R.K):
    """คืนตัวชี้วัดรายออเดอร์ (เรียงเหมือนกันทุกวิธี เพื่อเทียบแบบจับคู่ได้)

    new_only=True: เฉพาะเมนูที่ลูกค้ายังไม่เคยสั่ง
    ข้ามออเดอร์ที่ผู้สมัครไม่เกิน min_cand เมนู
    """
    cust, shop, rows = [], [], []
    for c, t, s, items in orders:
        cand = ds.shop_rows[s]
        target = set(items)
        if new_only:
            sn = seen.get(c, {})
            cand = np.array([i for i in cand if i not in sn])
            target = {i for i in items if i not in sn}
            if not target:
                continue
        if len(cand) <= min_cand:
            continue
        acc = np.zeros(len(METRICS))
        for _ in range(repeats):
            acc += order_metrics(rank(c, cand), target)
        cust.append(c)
        shop.append(s)
        rows.append(acc / repeats)
    m = np.array(rows) if rows else np.zeros((0, len(METRICS)))
    mean = m.mean(0) if len(m) else np.zeros(len(METRICS))
    return {"cust": np.array(cust), "shop": np.array(shop), "m": m, "mean": dict(zip(METRICS, mean)), "n": len(m)}


def bootstrap_ci(cust, values, b=BOOTSTRAP, seed=0):
    """ช่วงความเชื่อมั่น 95% ของค่าเฉลี่ย โดยสุ่มเลือก "ลูกค้า" (ไม่ใช่ออเดอร์) เพราะออเดอร์ของคนเดียวกันสัมพันธ์กัน"""
    if len(values) == 0:
        return 0.0, 0.0
    uniq, inv = np.unique(cust, return_inverse=True)
    sums = np.bincount(inv, weights=values, minlength=len(uniq))
    cnts = np.bincount(inv, minlength=len(uniq)).astype(float)
    idx = np.random.default_rng(seed).integers(0, len(uniq), size=(b, len(uniq)))
    est = sums[idx].sum(1) / cnts[idx].sum(1)
    lo, hi = np.percentile(est, [2.5, 97.5])
    return float(lo), float(hi)


# ---------------------------------------------------------------------
# จูน
# ---------------------------------------------------------------------
def valid_hit(ds, rank, valid, seen_train, new_only=False):
    r = evaluate(ds, rank, valid, seen_train, new_only)
    return r["mean"]["HitRate@5"] if r["n"] else -1.0


def tune_grid(ds, train, valid, sales, seen_train):
    best, best_score = None, -1.0
    for wt in (0.5, 1.0, 2.0):
        weights = {"ingredient": 1.0, "method": 1.0, "taste": wt, "price": 0.5}
        Xw = R.apply_weights(ds.X, ds.vocab, weights)
        for hl in (0, 4):
            states = build_states(train, Xw, hl)
            for rp, pp in product([0.0, 0.5, 1.0, 3.0], [0.0, 0.3, 1.0]):
                params = {"repeat": rp, "pop": pp}
                score = valid_hit(ds, make_cbf_tuned(Xw, states, sales, params), valid, seen_train)
                if score > best_score:
                    best, best_score = (weights, hl, params), score
    return best, best_score


def tune_optuna(ds, train, valid, sales, seen_train, n_trials, seed):
    def objective(trial):
        weights = {
            "ingredient": 1.0,
            "method": trial.suggest_float("w_method", 0.1, 5.0, log=True),
            "taste": trial.suggest_float("w_taste", 0.1, 5.0, log=True),
            "price": trial.suggest_float("w_price", 0.1, 5.0, log=True),
        }
        hl = trial.suggest_categorical("half_life", [0, 2, 4, 8])
        params = {"repeat": trial.suggest_float("repeat", 0.0, 3.0), "pop": trial.suggest_float("pop", 0.0, 2.0)}
        return valid_hit(ds, cbf_ranker(ds, train, sales, weights, hl, params), valid, seen_train)

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=n_trials)
    bp = study.best_params
    weights = {"ingredient": 1.0, "method": bp["w_method"], "taste": bp["w_taste"], "price": bp["w_price"]}
    return (weights, bp["half_life"], {"repeat": bp["repeat"], "pop": bp["pop"]}), study.best_value


def lr_training_set(ds, orders, hl, only_unseen):
    """1 แถว = (ออเดอร์หนึ่ง, เมนูผู้สมัครหนึ่งเมนูในร้านนั้น) ฟีเจอร์ใช้เฉพาะประวัติก่อนออเดอร์นั้น
    ยอดขายตัดออเดอร์ปัจจุบันออกก่อน (กันข้อมูลรั่ว) ออเดอร์แรกของลูกค้าไม่มีประวัติจึงข้าม"""
    sales = sales_vector(orders, len(ds.menus))
    rows, labels = [], []
    for c, oc in orders_by_customer(orders).items():
        hist = [items for _, items in oc]
        for k in range(1, len(oc)):
            prof, _, raw = R.customer_state(hist[:k], ds.X, hl)
            shop, items = oc[k]
            cand = ds.shop_rows[shop]
            if only_unseen:
                cand = np.array([i for i in cand if raw.get(i, 0) == 0])
                if len(cand) < 2:
                    continue
            y = np.isin(cand, list(items)).astype(int)
            if only_unseen and y.sum() == 0:
                continue
            sv = sales.copy()
            sv[list(items)] -= 1
            raw_c = np.array([raw.get(i, 0) for i in cand], dtype=float)
            rows.append(R.lr_features(prof, raw_c, ds.X[cand], sv[cand], ds.slices))
            labels.append(y)
    return np.vstack(rows), np.concatenate(labels)


def fit_lr(ds, orders, hl, C, only_unseen):
    F, y = lr_training_set(ds, orders, hl, only_unseen)
    return LogisticRegression(C=C, max_iter=1000).fit(F, y)


def tune_logreg(ds, train, valid, sales, seen_train, only_unseen):
    best = (None, None, -1.0)
    for hl in (0, 4):
        states = build_states(train, ds.X, hl)
        F, y = lr_training_set(ds, train, hl, only_unseen)
        for C in (0.01, 0.1, 1.0, 10.0):
            model = LogisticRegression(C=C, max_iter=1000).fit(F, y)
            rank = make_lr(ds, states, sales, model.coef_[0], model.intercept_[0])
            score = valid_hit(ds, rank, valid, seen_train, new_only=only_unseen)
            if score > best[2]:
                best = (hl, C, score)
    return best


# ---------------------------------------------------------------------
# รายงาน
# ---------------------------------------------------------------------
def report_table(results, title, methods):
    print(f"\n-- {title} --")
    base = results["เมนูขายดี"]
    out = {}
    for name in methods:
        r = results[name]
        hit = r["m"][:, 0]
        lo, hi = bootstrap_ci(r["cust"], hit)
        diff = hit - base["m"][:, 0]
        dlo, dhi = bootstrap_ci(r["cust"], diff)
        mark = "  (ดีกว่าขายดี)" if dlo > 0 else "  (แย่กว่าขายดี)" if dhi < 0 else ""
        mm = r["mean"]
        if name == "เมนูขายดี":
            delta = ""
        else:
            delta = f" Δ={diff.mean():+.3f} [{dlo:+.3f},{dhi:+.3f}]{mark}"
        print(
            f"{name:26s} Hit@5={mm['HitRate@5']:.3f} [{lo:.3f},{hi:.3f}] P@5={mm['Precision@5']:.3f} "
            f"R@5={mm['Recall@5']:.3f} MRR={mm['MRR']:.3f} NDCG@5={mm['NDCG@5']:.3f}{delta}"
        )
        out[name] = {
            **{k: float(v) for k, v in mm.items()},
            "hit_ci95": [lo, hi],
            "delta_vs_popular": None if name == "เมนูขายดี" else {"mean": float(diff.mean()), "ci95": [dlo, dhi]},
            "n": r["n"],
        }
    print(f"   n={base['n']} ออเดอร์ จาก {len(np.unique(base['cust']))} ลูกค้า | [ ] = ช่วงความเชื่อมั่น 95% | Δ = ผลต่างเทียบเมนูขายดี")
    return out


def report_per_shop(results, ds, methods):
    shops = sorted(set(results[methods[0]]["shop"]))
    if not shops:
        return
    print("\n-- Hit@5 แยกรายร้าน (ทุกเมนู) --")
    print(f"{'':26s}" + "".join(f"{'ร้าน' + str(s):>9s}" for s in shops))
    ns = {s: int((results[methods[0]]["shop"] == s).sum()) for s in shops}
    print(f"{'(จำนวนออเดอร์ทดสอบ)':26s}" + "".join(f"{ns[s]:>9d}" for s in shops))
    for name in methods:
        r = results[name]
        cells = []
        for s in shops:
            mask = r["shop"] == s
            cells.append(f"{r['m'][mask, 0].mean():>9.3f}" if mask.any() else f"{'-':>9s}")
        print(f"{name:26s}" + "".join(cells))
    print("   เมนูผู้สมัครต่อร้าน: " + ", ".join(f"ร้าน{s}={len(ds.shop_rows[s])}" for s in shops))


# ---------------------------------------------------------------------
# ควบคุมการทดลอง
# ---------------------------------------------------------------------
def run(snap: dict, n_trials: int, seed: int, do_grid: bool) -> dict:
    t0 = time.time()
    ds = Dataset(snap)
    customers = {o[0] for o in ds.orders}
    print(f"ข้อมูล: เมนู {len(ds.menus)} | ลูกค้า {len(customers)} | ออเดอร์ที่ใช้ {len(ds.orders)} "
          f"(ตัดทิ้งเพราะไม่เหลือรายการ {ds.n_orders_dropped})")
    print("มิติเวกเตอร์เมนู: " + ", ".join(f"{g}={s.stop - s.start}" for g, s in ds.slices.items()) + f" (รวม {ds.dim})")
    train, valid, test = split(ds.orders)
    full_train = train + valid
    print(f"แบ่งข้อมูล: train={len(train)} valid={len(valid)} test={len(test)}")

    sales_tr = sales_vector(train, len(ds.menus))
    seen_tr = seen_of(build_states(train, ds.X, 0))

    tuned: dict = {}
    if do_grid:
        (gw, ghl, gp), gs = tune_grid(ds, train, valid, sales_tr, seen_tr)
        tuned["grid"] = {"weights": gw, "half_life": ghl, "params": gp, "valid_hit": gs}
        print(f"[Grid] valid Hit@5={gs:.3f} half_life={ghl} {gp} weights={gw}")
    (ow, ohl, op), os_ = tune_optuna(ds, train, valid, sales_tr, seen_tr, n_trials, seed)
    tuned["optuna"] = {"weights": ow, "half_life": ohl, "params": op, "valid_hit": os_, "trials": n_trials}
    print(f"[Optuna {n_trials} รอบ] valid Hit@5={os_:.3f} half_life={ohl} {op}")
    print("          weights=" + ", ".join(f"{k}={v:.2f}" for k, v in ow.items()))

    lr_cfg = {}
    for key, only_unseen in (("lr_all", False), ("lr_new", True)):
        hl, C, sc = tune_logreg(ds, train, valid, sales_tr, seen_tr, only_unseen)
        lr_cfg[key] = (hl, C, sc, only_unseen)
        print(f"[LR {'เมนูใหม่' if only_unseen else 'ทุกเมนู'}] valid Hit@5={sc:.3f} half_life={hl} C={C}")

    # ฝึกรอบสุดท้ายบน train+valid แล้วประเมินบน test
    sales = sales_vector(full_train, len(ds.menus))
    plain_states = build_states(full_train, ds.X, 0)
    seen = seen_of(plain_states)
    rankers = {
        "สุ่ม": make_random(),
        "เมนูขายดี": make_popular(sales),
        "เคยสั่งบ่อย+ขายดี": make_repeat_popular(plain_states, sales),
        "Filter แท็กโปรด": make_favorite(ds, plain_states, sales),
        "CBF พื้นฐาน": make_cbf_basic(ds, plain_states, sales),
    }
    if do_grid:
        g = tuned["grid"]
        rankers["CBF ปรับน้ำหนัก (Grid)"] = cbf_ranker(ds, full_train, sales, g["weights"], g["half_life"], g["params"])
    rankers["CBF ปรับน้ำหนัก (Optuna)"] = cbf_ranker(ds, full_train, sales, ow, ohl, op)
    for key, name in (("lr_all", "LR ทุกเมนู"), ("lr_new", "LR เมนูใหม่")):
        hl, C, sc, only_unseen = lr_cfg[key]
        model = fit_lr(ds, full_train, hl, C, only_unseen)
        coef, intercept = model.coef_[0], float(model.intercept_[0])
        rankers[name] = make_lr(ds, build_states(full_train, ds.X, hl), sales, coef, intercept)
        tuned[key] = {
            "half_life": hl, "C": C, "valid_hit": sc, "feature_names": list(R.FEATURE_NAMES),
            "coef": [float(x) for x in coef], "intercept": intercept,
        }
        print(f"   coef {name}: " + ", ".join(f"{n}={w:+.2f}" for n, w in zip(R.FEATURE_NAMES, coef)))

    methods = [m for m in METHODS if m in rankers]
    summary = {}
    for new_only in (False, True):
        results = {}
        for name in methods:
            rep = RANDOM_REPEATS if name == "สุ่ม" else 1
            results[name] = evaluate(ds, rankers[name], test, seen, new_only, repeats=rep)
        title = "เมนูที่ยังไม่เคยสั่ง" if new_only else "ทุกเมนู"
        summary["new_only" if new_only else "all"] = report_table(results, title, methods)
        if not new_only:
            report_per_shop(results, ds, methods)

    out = {
        "snapshot_fetched_at": snap.get("fetched_at"),
        "k": R.K,
        "vocab": ds.vocab,
        "counts": {"menus": len(ds.menus), "customers": len(customers), "orders": len(ds.orders),
                   "train": len(train), "valid": len(valid), "test": len(test)},
        "tuned": tuned,
        "metrics": summary,
    }
    print(f"\nใช้เวลา {time.time() - t0:.0f} วินาที")
    return out


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="ฝึก/จูน/เทียบวิธีแนะนำเมนูบนข้อมูลจริง")
    ap.add_argument("--trials", type=int, default=N_TRIALS, help="จำนวนรอบ Optuna")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--no-grid", action="store_true", help="ข้าม grid search เดิม")
    args = ap.parse_args()
    if not SNAPSHOT.exists():
        sys.exit(f"ไม่พบ {SNAPSHOT} ให้รัน python -m model.fetch_data ก่อน")
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    result = run(snap, args.trials, args.seed, not args.no_grid)
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"บันทึกผลแล้ว: {RESULT}")


if __name__ == "__main__":
    main()
