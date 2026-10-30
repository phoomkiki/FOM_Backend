# FOMBackend API Flow

Base path: `/api/v1`. Interactive API documentation: `/docs`.

## Authentication and profile
- `POST /auth/line`: verify LINE ID token; new users receive customer role.
- `POST /auth/admin`: verify email/password with Supabase Auth and require a linked `users.auth_id` row whose role is admin.
- `GET /auth/me`, `POST /auth/logout`.
- `GET/PATCH /profile/me`: view/update the current profile and record PDPA consent.

Send `Authorization: Bearer <access_token>` for protected endpoints. Guest delivery sessions receive a separate short-lived `rider_token`.

## Shops and catalog
- `GET /shops`, `GET /shops/{shop_id}`, `GET /shops/mine`, `POST /shops`, `PATCH /shops/{shop_id}`.
- Shop creation makes the current user an owner and creates a pending shop. An admin must approve it before it is publicly listed or can accept orders.
- `GET/POST /categories`, `PATCH/DELETE /categories/{category_id}` (writes require admin).
- `GET/POST /menus`, `GET/PATCH/DELETE /menus/{menu_id}`.
- `GET /menus/{menu_id}/options`, `POST /menus/{menu_id}/option-groups`, `POST /option-groups/{group_id}/options`.
- `GET/POST /tags`; tag proposals from owners are pending. Admin reviews tags at `GET /admin/tags` and `PATCH /admin/tags/{tag_id}/review`.
- `POST/DELETE /menus/{menu_id}/tags/{tag_id}`.

## Addresses and orders
- `GET/POST /addresses`, `PATCH/DELETE /addresses/{address_id}`.
- `POST /orders`: server fetches menu/option prices, validates availability and required options, computes totals, and snapshots the address/menu details.
- `GET /orders/mine`, `GET /orders/{order_id}`, `GET /shops/{shop_id}/orders`.
- `PATCH /orders/{order_id}/status`: checks allowed status transitions and owner/customer/admin permissions.

Order status flow:
`pending_payment -> paid -> accepted -> preparing -> ready -> in_delivery -> delivered`.
Cancellation/refund transitions are restricted; payment approval is not a normal client status update.

## Payments
- `POST /payments`: creates a payment attempt with an amount-specific PromptPay EMV payload and 15-minute expiry.
- `POST /payments/{payment_id}/slip`: submit a slip image URL for review.
- `GET /payments/mine`.
- Admin reviews at `GET /admin/payments` and `PATCH /admin/payments/{payment_id}/review`.

A generated QR payload is not proof of payment. This version uses admin review of the submitted slip; automated bank/provider transaction verification is not implemented yet. The frontend should render the returned `qr_payload` as a QR image.

## Delivery QR and guest rider
- `POST /delivery-batches`: owner/admin creates one expiring QR token for multiple ready orders from the same shop. Only the token hash is persisted.
- `GET /delivery-batches/scan/{token}`: read tasks after scanning.
- `POST /delivery-batches/scan/{token}/claim`: guest rider claims the batch with name and phone and receives `rider_token`.
- `POST /deliveries/{delivery_id}/complete`: requires `Authorization: Bearer <rider_token>` and a proof-image URL. Each order is confirmed independently.
- Admin can list batches/deliveries and revoke an active batch.

Upload photos to an approved object-storage bucket and send the resulting URL. Do not send large base64 image strings through these endpoints.

## Admin
- `GET /admin/overview`
- `GET /admin/users`, `PATCH /admin/users/{user_id}/role`
- `GET /admin/shops`, `PATCH /admin/shops/{shop_id}/approval`
- `GET /admin/orders`, `GET /admin/payments`, `PATCH /admin/payments/{payment_id}/review`
- `GET /admin/deliveries`, `GET /admin/delivery-batches`, `POST /admin/delivery-batches/{batch_id}/revoke`
- `GET /admin/tags`, `PATCH /admin/tags/{tag_id}/review`

## Important deployment notes
- This implementation intentionally does not run Alembic or mutate the database schema.
- Several endpoints require the new columns/tables from the updated SQLAlchemy models. Until the separate migration is applied, those endpoints may return a schema-related 422/502 from Supabase.
- Multi-table order creation and delivery-batch creation currently use multiple PostgREST requests and are not atomic. Before production, move these multi-row workflows into PostgreSQL RPC functions/transactions and add idempotency protection.
- Payment verification is manual. Do not enable auto-fulfillment based only on client-supplied slip URLs.
- Use Supabase Storage signed upload URLs or another controlled upload endpoint for delivery proofs and payment slips.
- Guest rider QR tokens expire; claim returns a short-lived bearer token. Do not log or share either raw token.
