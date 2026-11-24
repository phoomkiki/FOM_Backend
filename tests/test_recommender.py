"""ทดสอบแกนคำนวณระบบแนะนำ (ไม่ต้องใช้ฐานข้อมูล)"""
import numpy as np
import pytest

from app.services import recommender as R

TAGS = [
    {"tag_id": 1, "tag_type": "ingredient", "status": "approved"},
    {"tag_id": 2, "tag_type": "ingredient", "status": "approved"},
    {"tag_id": 3, "tag_type": "taste", "status": "approved"},
    {"tag_id": 4, "tag_type": "cooking_method", "status": "approved"},
    {"tag_id": 5, "tag_type": "ingredient", "status": "pending"},
    {"tag_id": 6, "tag_type": "something_else", "status": "approved"},
]
VOCAB = R.build_vocab(TAGS)
MENUS = [
    {"menu_id": 1, "price": 40},
    {"menu_id": 2, "price": 40},
    {"menu_id": 3, "price": 80},
]
TAGS_OF = {1: {1, 3}, 2: {2}, 3: {1}}
PARAMS = {"half_life": 0, "coef": [2, 0, 0, 0, 0, 0], "intercept": 0.0}


def test_price_bucket_edges():
    assert [R.price_bucket(p) for p in (10, 49.99, 50, 70, 70.01, 180)] == [0, 0, 1, 1, 2, 2]


def test_vocab_keeps_only_approved_known_types():
    assert VOCAB == {"ingredient": [1, 2], "method": [4], "taste": [3]}


def test_group_slices_cover_the_vector():
    sl, dim = R.group_slices(VOCAB)
    assert (sl["ingredient"], sl["method"], sl["taste"], sl["price"]) == (
        slice(0, 2), slice(2, 3), slice(3, 4), slice(4, 7))
    assert dim == 7


def test_menu_matrix_marks_tags_and_price_bucket():
    X = R.menu_matrix(MENUS, TAGS_OF, VOCAB)
    # เมนู 1: ingredient#1, taste#3, ราคา <50
    assert X[0].tolist() == [1, 0, 0, 1, 1, 0, 0]
    # เมนู 3: ingredient#1, ราคา >70
    assert X[2].tolist() == [1, 0, 0, 0, 0, 0, 1]


def test_menu_matrix_ignores_unapproved_tags():
    X = R.menu_matrix([{"menu_id": 9, "price": 60}], {9: {5, 6}}, VOCAB)
    assert X[0].tolist() == [0, 0, 0, 0, 0, 1, 0]  # มีแต่ช่วงราคา


def test_customer_state_half_life_weights_recent_orders_more():
    X = np.eye(3)
    prof, weighted, raw = R.customer_state([[0], [1]], X, half_life=1)
    assert weighted == {0: 0.5, 1: 1.0}
    assert raw == {0: 1, 1: 1}
    assert prof.tolist() == [0.5, 1.0, 0.0]
    assert R.customer_state([], X, 1) is None


def test_cosine_with_zero_profile_is_zero_not_nan():
    out = R.cosine(np.zeros(3), np.eye(3))
    assert not np.isnan(out).any() and out.tolist() == [0, 0, 0]


def rank(history, candidates=(1, 2, 3), **kw):
    sales = kw.pop("sales", {1: 5, 2: 9, 3: 1})
    return R.rank_for_customer(MENUS, TAGS_OF, VOCAB, history, sales, list(candidates), PARAMS, **kw)


def test_personalized_ranking_prefers_matching_ingredient_and_breaks_ties_by_id():
    strategy, ranked = rank([[1]])
    assert strategy == "personalized"
    # เมนู 1 และ 3 วัตถุดิบตรงกับที่เคยสั่ง (คะแนนเท่ากัน -> เรียงตาม id) เมนู 2 ท้ายสุด
    assert [m for m, _ in ranked] == [1, 3, 2]


def test_new_only_excludes_menus_already_ordered():
    _, ranked = rank([[1]], new_only=True)
    assert [m for m, _ in ranked] == [3, 2]


def test_cold_start_falls_back_to_popularity():
    strategy, ranked = rank([])
    assert strategy == "popular_fallback"
    assert [m for m, _ in ranked] == [2, 1, 3]
    assert all(0 <= s <= 1 for _, s in ranked)


def test_limit_and_unknown_ids_are_handled():
    _, ranked = rank([[999, 1]], candidates=(1, 2, 3, 404), limit=2)
    assert [m for m, _ in ranked] == [1, 3]  # 999 (ถูกลบ/ไม่รู้จัก) และ 404 ถูกข้ามอย่างเงียบ ๆ


def test_no_candidates_returns_empty():
    assert rank([[1]], candidates=())[1] == []
    assert rank([[1]], new_only=True, candidates=(1,))[1] == []


def test_bad_coef_length_is_rejected():
    with pytest.raises(ValueError):
        R.rank_for_customer(MENUS, TAGS_OF, VOCAB, [], {}, [1], {"half_life": 0, "coef": [1, 2], "intercept": 0}, 5)
