"""Small server-side client for the Supabase PostgREST API."""

import httpx
from fastapi import HTTPException

from app.core.config import settings

USER_FIELDS = "user_id,auth_id,line_user_id,display_name,img_url,refund_promptpay_id,refund_account_name,pdpa_consent_at,pdpa_consent_version,location_consent_at,created_at"


def _config() -> tuple[str, str]:
    base_url = (settings.supabase_url or "").strip().rstrip("/")
    if base_url.endswith("/rest/v1"):
        base_url = base_url[:-len("/rest/v1")]
    service_key = (settings.supabase_service_role_key or "").strip()
    if not base_url or not service_key:
        raise HTTPException(status_code=503, detail="Supabase Data API is not configured on the server.")
    return base_url, service_key


def _headers(service_key: str) -> dict[str, str]:
    headers = {"apikey": service_key, "Content-Type": "application/json"}
    if service_key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {service_key}"
    return headers


async def find_user_by_line_id(line_user_id: str) -> dict | None:
    base_url, service_key = _config()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{base_url}/rest/v1/users", headers=_headers(service_key),
                params={"select": USER_FIELDS, "line_user_id": f"eq.{line_user_id}", "limit": "1"},
            )
            response.raise_for_status()
            rows = response.json()
            return rows[0] if rows else None
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "Could not query the FOM user record in Supabase.") from exc


async def create_line_user(line_user_id: str, display_name: str, img_url: str | None = None) -> dict:
    base_url, service_key = _config()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{base_url}/rest/v1/users",
                headers={**_headers(service_key), "Prefer": "return=representation"},
                json={"line_user_id": line_user_id, "display_name": display_name, "img_url": img_url},
            )
            if response.status_code == 409:
                existing = await find_user_by_line_id(line_user_id)
                if existing:
                    return existing
            response.raise_for_status()
            rows = response.json()
            if not rows:
                raise HTTPException(502, "Supabase did not return the newly created user.")
            return rows[0]
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "Could not create the FOM user in Supabase.") from exc


async def update_user_img_url(line_user_id: str, img_url: str) -> dict | None:
    base_url, service_key = _config()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(
                f"{base_url}/rest/v1/users", headers={**_headers(service_key), "Prefer": "return=representation"},
                params={"line_user_id": f"eq.{line_user_id}"}, json={"img_url": img_url},
            )
            response.raise_for_status()
            rows = response.json()
            return rows[0] if rows else await find_user_by_line_id(line_user_id)
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "Could not update the FOM user image URL in Supabase.") from exc


async def get_user_by_id(user_id: int) -> dict | None:
    base_url, service_key = _config()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{base_url}/rest/v1/users", headers=_headers(service_key),
                params={"select": USER_FIELDS, "user_id": f"eq.{user_id}", "limit": "1"},
            )
            response.raise_for_status()
            rows = response.json()
            return rows[0] if rows else None
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "Could not query the FOM user record in Supabase.") from exc


async def find_user_by_auth_id(auth_id: str) -> dict | None:
    base_url, service_key = _config()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{base_url}/rest/v1/users", headers=_headers(service_key),
                params={"select": USER_FIELDS, "auth_id": f"eq.{auth_id}", "limit": "1"},
            )
            response.raise_for_status()
            rows = response.json()
            return rows[0] if rows else None
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "Could not query the admin user record in Supabase.") from exc
