# Supabase Database Alignment

Checked against the live Supabase PostgREST OpenAPI schema on 2026-10-16. Runtime code uses the existing database schema; no database migrations or data mutations were run during this alignment.

## Schema-aligned behavior
- User fields are restricted to columns present in `public.users`. Phone is read/written through a user's default row in `addresses`.
- Shop listing and menu discovery use `shops.is_open`; shop approval fields do not exist in the current database.
- Categories are shop-scoped (`shop_id`, `category_name`, `sort_order`).
- Orders save the delivery address snapshot to the `delivery_*` columns and use the database's order statuses.
- Payment review uses `payments.status` values such as `waiting_slip`, `manual_check`, `manual_passed`, and `manual_failed`.
- Delivery QR tokens are signed JWTs stored in `delivery_batches.qr_token`; batch states use `active`, `completed`, and `cancelled`. Delivery proof is stored in `deliveries`, keyed by `order_id`.
- Refunds use the database's `pending` / `refunded` states and real columns. The reason/admin note are retained in `activity_logs`.
- Privacy request type is included in `privacy_requests.reason`, since there is no `request_type` column.

## Endpoints constrained by the current schema
- `PATCH /api/v1/admin/users/{user_id}/role` returns HTTP 409 rather than writing a nonexistent `users.role`. Admin role belongs in Supabase Auth `app_metadata`; owner role is derived from `shops.owner_id`.
- `PATCH /api/v1/admin/shops/{shop_id}/approval` returns HTTP 409 because `shops` has no approval-state/audit columns. `is_open` is not treated as an approval state.

To support those moderation workflows fully, the database schema must first be intentionally extended and reviewed. No schema changes are made by this code alignment.
