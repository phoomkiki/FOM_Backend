"""แกนคำนวณระบบแนะนำเมนู (numpy ล้วน)

ใช้ร่วมกันทั้งตอนฝึก (model/train.py) และตอนให้บริการ (API) เพื่อให้คะแนนตรงกันเสมอ
ห้าม import sklearn / optuna ในไฟล์นี้ เพราะไฟล์นี้ถูก deploy ขึ้น Vercel

แนวคิดเหมือนสคริปต์จำลองเดิม (train_model.py / tune_model.py):
  - เมนู 1 เมนู = เวกเตอร์ multi-hot ของแท็กที่อนุมัติแล้ว 3 กลุ่ม (ingredient, method, taste)
    ต่อด้วย one-hot ของช่วงราคา 3 ช่วง
  - โปรไฟล์ลูกค้า = ผลรวมเวกเตอร์เมนูที่เคยสั่ง (ถ่วงน้ำหนักด้วย half-life นับเป็น "จำนวนออเดอร์")
  - ให้คะแนนเมนูผู้สมัครในร้านเดียวกันแล้วเรียงจากมากไปน้อย
"""
from __future__ import annotations

import numpy as np

K = 5
GROUPS = ("ingredient", "method", "taste", "price")  # ลำดับคอลัมน์ในเวกเตอร์เมนู
TAG_GROUPS = ("ingredient", "method", "taste")
TAG_TYPE_TO_GROUP = {"ingredient": "ingredient", "cooking_method": "method", "taste": "taste"}
PRICE_EDGES = (50, 70)  # <50 | 50-70 | >70
N_PRICE = 3
FEATURE_NAMES = tuple("sim_" + g for g in GROUPS) + ("mine", "pop")


# ---------------------------------------------------------------------
# เวกเตอร์เมนู
# ---------------------------------------------------------------------
def price_bucket(price: float) -> int:
    """0 = <50, 1 = 50-70 (รวมขอบ), 2 = >70"""
    if price < PRICE_EDGES[0]:
        return 0
    if price <= PRICE_EDGES[1]:
        return 1
    return 2


def build_vocab(tags) -> dict[str, list[int]]:
    """รายการ tag_id ต่อกลุ่ม (เรียงตาม tag_id) เฉพาะแท็กที่ status = approved"""
    vocab: dict[str, list[int]] = {g: [] for g in TAG_GROUPS}
    for t in sorted(tags, key=lambda t: t["tag_id"]):
        if t.get("status") != "approved":
            continue
        g = TAG_TYPE_TO_GROUP.get(t["tag_type"])
        if g:
            vocab[g].append(t["tag_id"])
    return vocab


def group_slices(vocab: dict[str, list[int]]) -> tuple[dict[str, slice], int]:
    """ตำแหน่งคอลัมน์ของแต่ละกลุ่ม และจำนวนมิติรวม"""
    sl: dict[str, slice] = {}
    start = 0
    for g in GROUPS:
        n = N_PRICE if g == "price" else len(vocab[g])
        sl[g] = slice(start, start + n)
        start += n
    return sl, start


def menu_matrix(menus, tags_of_menu, vocab) -> np.ndarray:
    """เมทริกซ์เมนู (ยังไม่ถ่วงน้ำหนัก)

    menus: รายการ dict ที่มี menu_id และ price (ลำดับแถวตามลำดับที่ส่งมา)
    tags_of_menu: {menu_id: {tag_id, ...}}
    """
    sl, dim = group_slices(vocab)
    pos = {g: {tid: j for j, tid in enumerate(vocab[g])} for g in TAG_GROUPS}
    X = np.zeros((len(menus), dim))
    for r, m in enumerate(menus):
        for tid in tags_of_menu.get(m["menu_id"], ()):
            for g in TAG_GROUPS:
                j = pos[g].get(tid)
                if j is not None:
                    X[r, sl[g].start + j] = 1.0
        X[r, sl["price"].start + price_bucket(float(m["price"]))] = 1.0
    return X


def apply_weights(X: np.ndarray, vocab, weights: dict[str, float]) -> np.ndarray:
    """คูณน้ำหนักรายกลุ่ม (กลุ่มที่ไม่ระบุ = 1.0)"""
    sl, _ = group_slices(vocab)
    w = np.ones(X.shape[1])
    for g, s in sl.items():
        w[s] = weights.get(g, 1.0)
    return X * w


def cosine(u: np.ndarray, m: np.ndarray) -> np.ndarray:
    nu = np.linalg.norm(u)
    nm = np.linalg.norm(m, axis=1)
    return (m @ u) / (nu * nm + 1e-9)


# ---------------------------------------------------------------------
# สถานะของลูกค้า 1 คน
# ---------------------------------------------------------------------
def customer_state(history, X: np.ndarray, half_life: float):
    """history: รายการออเดอร์เรียงจากเก่าไปใหม่ แต่ละออเดอร์เป็นรายการ "แถวเมนู" (ไม่ซ้ำ)

    คืน (โปรไฟล์, จำนวนครั้งที่เคยสั่งแบบถ่วงน้ำหนัก, จำนวนครั้งที่เคยสั่งจริง) หรือ None ถ้าไม่มีประวัติ
    half_life นับเป็นจำนวนออเดอร์ (0 = ไม่ถ่วง)
    """
    if not history:
        return None
    last = len(history) - 1
    prof = np.zeros(X.shape[1])
    weighted: dict[int, float] = {}
    raw: dict[int, int] = {}
    for t, items in enumerate(history):
        w = 0.5 ** ((last - t) / half_life) if half_life else 1.0
        for i in items:
            prof += w * X[i]
            weighted[i] = weighted.get(i, 0.0) + w
            raw[i] = raw.get(i, 0) + 1
    return prof, weighted, raw


# ---------------------------------------------------------------------
# วิธีเรียงลำดับ (คืนตำแหน่งของผู้สมัคร เรียงจากดีที่สุดไปแย่ที่สุด)
# ---------------------------------------------------------------------
def order_by_score(score: np.ndarray) -> np.ndarray:
    return np.argsort(-score, kind="stable")


def order_popular(pop_c: np.ndarray) -> np.ndarray:
    return np.argsort(-pop_c, kind="stable")


def order_repeat_popular(raw_c: np.ndarray, pop_c: np.ndarray) -> np.ndarray:
    """เคยสั่งบ่อยสุดก่อน เสมอกันให้ขายดีกว่าก่อน"""
    return np.lexsort((-pop_c, -raw_c))


def order_favorite_tag(prof, X_c, pop_c, ingredient_slice: slice) -> np.ndarray:
    """เมนูที่มีวัตถุดิบโปรดอันดับ 1 ของลูกค้าก่อน เสมอกันให้ขายดีกว่าก่อน"""
    if ingredient_slice.stop == ingredient_slice.start:
        return order_popular(pop_c)
    top = int(np.argmax(prof[ingredient_slice]))
    match = X_c[:, ingredient_slice.start + top] > 0
    return np.lexsort((-pop_c, ~match))


def order_cbf_basic(prof, X_c) -> np.ndarray:
    return order_by_score(cosine(prof, X_c))


def cbf_scores(prof, X_c, weighted_c, pop_c, repeat: float, pop: float) -> np.ndarray:
    """CBF ปรับน้ำหนัก = ความคล้าย + repeat * เคยสั่ง(0-1) + pop * ขายดี(0-1)"""
    sim = cosine(prof, X_c)
    mine = weighted_c / (weighted_c.max() + 1e-9)
    popn = pop_c / (pop_c.max() + 1e-9)
    return sim + repeat * mine + pop * popn


# ---------------------------------------------------------------------
# Logistic regression (ตอนให้บริการใช้แค่ค่า coef / intercept ที่ฝึกไว้)
# ---------------------------------------------------------------------
def lr_features(prof, raw_c, X_c, pop_c, slices) -> np.ndarray:
    """ฟีเจอร์ 6 ตัวต่อเมนู: ความคล้ายรายกลุ่ม 4 ตัว + เคยสั่ง + ขายดี (ทุกตัวอยู่ในช่วง 0-1)"""
    cols = [cosine(prof[slices[g]], X_c[:, slices[g]]) for g in GROUPS]
    cols.append(raw_c / (raw_c.max() + 1e-9))
    cols.append(pop_c / (pop_c.max() + 1e-9))
    return np.column_stack(cols)


def lr_scores(coef, intercept, features: np.ndarray) -> np.ndarray:
    return features @ np.asarray(coef) + float(intercept)


# ---------------------------------------------------------------------
# ใช้งานจริง: จัดอันดับเมนูให้ลูกค้า 1 คน (ใช้ค่าที่ฝึกไว้แล้วจาก recommender_params.py)
# ---------------------------------------------------------------------
def rank_for_customer(menus, tags_of_menu, vocab, history, sales, candidate_ids, params,
                      limit: int = K, new_only: bool = False):
    """จัดอันดับเมนูผู้สมัครด้วย Logistic regression ที่ฝึกไว้ แล้วคืน (strategy, [(menu_id, score), ...])

    menus:         รายการ dict (menu_id, price) ของเมนูผู้สมัครรวมเมนูที่ลูกค้าเคยสั่ง (ไว้สร้างโปรไฟล์)
    tags_of_menu:  {menu_id: {tag_id, ...}}
    vocab:         ผลของ build_vocab (สร้างจากแท็กที่อนุมัติ "ตอนนี้" ได้เลย เพราะโมเดลใช้แค่
                   ความคล้ายรายกลุ่ม ค่า coef จึงไม่ผูกกับรายชื่อแท็ก แท็กใหม่ใช้ได้โดยไม่ต้องฝึกใหม่)
    history:       ออเดอร์ของลูกค้าเรียงจากเก่าไปใหม่ แต่ละออเดอร์เป็นรายการ menu_id
    sales:         {menu_id: จำนวนออเดอร์ที่มีเมนูนี้}
    candidate_ids: menu_id ที่แนะนำได้ (ควรเรียงตาม menu_id เพื่อให้เสมอกันแล้วผลคงที่เหมือนตอนฝึก)
    params:        {"half_life", "coef", "intercept"}
    strategy:      "personalized" หรือ "popular_fallback" (ลูกค้ายังไม่มีประวัติ)
    """
    coef = list(params["coef"])
    if len(coef) != len(FEATURE_NAMES):
        raise ValueError(f"coef ต้องมี {len(FEATURE_NAMES)} ค่า แต่ได้ {len(coef)}")
    row = {m["menu_id"]: r for r, m in enumerate(menus)}
    X = menu_matrix(menus, tags_of_menu, vocab)
    slices, _ = group_slices(vocab)

    hist_rows = [sorted({row[i] for i in order if i in row}) for order in history]
    state = customer_state([o for o in hist_rows if o], X, params["half_life"])
    raw = state[2] if state else {}

    cand, seen_c = [], set()
    for i in candidate_ids:
        if i in row and i not in seen_c and not (new_only and row[i] in raw):
            cand.append(i)
            seen_c.add(i)
    strategy = "personalized" if state else "popular_fallback"
    if not cand:
        return strategy, []

    cand_rows = np.array([row[i] for i in cand])
    pop = np.array([float(sales.get(i, 0)) for i in cand])
    if state is None:
        score = pop / (pop.max() + 1e-9)
        order = order_popular(pop)
    else:
        raw_c = np.array([raw.get(row[i], 0) for i in cand], dtype=float)
        feats = lr_features(state[0], raw_c, X[cand_rows], pop, slices)
        score = lr_scores(coef, params["intercept"], feats)
        order = order_by_score(score)
    return strategy, [(cand[j], float(score[j])) for j in order[:limit]]
