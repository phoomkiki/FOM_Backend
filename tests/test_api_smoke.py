from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.main import app
from app.services.common import _promptpay_payload, ALLOWED_ORDER_TRANSITIONS

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "FOMBackend"


def test_protected_profile_requires_authentication():
    response = client.get("/api/v1/profile/me")
    assert response.status_code == 401


def test_profile_update_routes_are_split_by_purpose():
    paths = app.openapi()["paths"]
    assert "/api/v1/profile/refund-account" in paths
    assert "/api/v1/profile/addresses/{address_id}" in paths
    assert "/api/v1/profile/pdpa-consent" in paths
    assert "patch" not in paths["/api/v1/profile/me"]


def test_admin_api_requires_authentication():
    response = client.get("/api/v1/admin/overview")
    assert response.status_code == 401


def test_openapi_has_core_systems():
    paths = app.openapi()["paths"]
    assert "/api/v1/orders" in paths
    assert "/api/v1/payments" in paths
    assert "/api/v1/delivery-batches" in paths
    assert "/api/v1/admin/shops/{shop_id}/approval" in paths


def test_promptpay_payload_contains_fixed_amount_and_crc():
    payload = _promptpay_payload("0812345678", __import__("decimal").Decimal("123.45"))
    assert "5406123.45" in payload
    assert payload[-8:-4] == "6304"
    data = payload[:-4]
    crc = 0xFFFF
    for byte in data.encode("ascii"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    assert payload[-4:] == f"{crc:04X}"


def test_promptpay_rejects_invalid_payee_id():
    try:
        _promptpay_payload("12345", __import__("decimal").Decimal("10.00"))
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 422


def test_order_transition_map_matches_database_statuses():
    assert "completed" not in ALLOWED_ORDER_TRANSITIONS["pending_payment"]
    assert "preparing" in ALLOWED_ORDER_TRANSITIONS["paid"]
    assert "ready" in ALLOWED_ORDER_TRANSITIONS["preparing"]
    assert "completed" in ALLOWED_ORDER_TRANSITIONS["delivering"]
    assert "delivered" not in ALLOWED_ORDER_TRANSITIONS
