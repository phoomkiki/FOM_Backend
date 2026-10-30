# FOMBackend Service Structure

Service logic is separated by resource/domain instead of collecting all workflows in one `domain_service.py`.

- `auth_service.py` — LINE/Admin authentication and current principal
- `profile_service.py` — user profile
- `shop_service.py` — shops, shop hours, and shop orders
- `catalog_service.py` — categories, menus, options, and tags
- `address_service.py` — customer addresses
- `order_service.py` — order creation, listing, and status transitions
- `payment_service.py` — payment and slip review workflows
- `delivery_service.py` — delivery batches, guest rider flow, and delivery administration
- `admin_service.py` — admin overview, users, shop moderation, orders, and tag review
- `refund_service.py` — refund requests and review
- `privacy_service.py` — privacy requests and review
- `common.py` — shared authorization helpers, PromptPay payload builder, and order transition constants
- `data_api.py` / `supabase_rest.py` — shared Supabase data-access functions

`app/api/v1/*.py` files define HTTP routes and delegate business logic to the matching service module. `app/api/v1/domain.py` only aggregates the resource routers.

The previous monolithic service was preserved as `domain_service.py.bak-split-services` for recovery; it is not imported by the application.
