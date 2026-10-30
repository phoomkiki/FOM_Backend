"""Small safe PostgREST client used by FOM domain APIs."""
from typing import Any
import httpx
from fastapi import HTTPException
from app.core.config import settings
from app.services.supabase_rest import _headers


def _base() -> tuple[str, str]:
    url = (settings.supabase_url or "").strip().rstrip("/")
    if url.endswith("/rest/v1"):
        url = url[:-8]
    key = (settings.supabase_service_role_key or "").strip()
    if not url or not key:
        raise HTTPException(503, "Supabase Data API is not configured.")
    return url + "/rest/v1", key


async def request_table(method: str, table: str, *, params: dict[str, Any] | None = None,
                        body: Any = None, prefer: str | None = "return=representation") -> Any:
    base, key = _base()
    headers = _headers(key)
    if prefer:
        headers["Prefer"] = prefer
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.request(
                method, f"{base}/{table}", headers=headers, params=params,
                json=body if body is not None else None,
            )
        if response.status_code >= 400:
            # Keep internal database errors out of client responses.
            if response.status_code in (401, 403):
                raise HTTPException(502, "Supabase rejected the server-side database request.")
            if response.status_code == 404:
                raise HTTPException(404, f"Resource not found in {table}.")
            if response.status_code == 409:
                raise HTTPException(409, "The operation conflicts with existing data.")
            if response.status_code == 400:
                raise HTTPException(422, "The submitted data is invalid for the current database schema.")
            raise HTTPException(502, f"Database request failed ({response.status_code}).")
        if response.status_code == 204 or not response.content:
            return None
        return response.json()
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "Could not communicate with Supabase.") from exc


async def select_rows(table: str, *, select: str = "*", filters: dict[str, str] | None = None,
                      order: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
    params: dict[str, Any] = {"select": select, "limit": str(min(max(limit, 1), 100)), "offset": str(max(offset, 0))}
    if filters:
        params.update(filters)
    if order:
        params["order"] = order
    rows = await request_table("GET", table, params=params, prefer=None)
    return rows or []


async def get_one(table: str, filters: dict[str, str], select: str = "*") -> dict | None:
    rows = await select_rows(table, select=select, filters=filters, limit=1)
    return rows[0] if rows else None


async def insert_rows(table: str, rows: dict | list[dict]) -> list[dict]:
    result = await request_table("POST", table, body=rows)
    return result or []


async def patch_rows(table: str, filters: dict[str, str], body: dict) -> list[dict]:
    return await request_table("PATCH", table, params=filters, body=body) or []


async def delete_rows(table: str, filters: dict[str, str]) -> None:
    await request_table("DELETE", table, params=filters, prefer="return=minimal")
