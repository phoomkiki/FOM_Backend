"""Create FOM ordering schema matching the Supabase public tables.

Revision ID: 0002_fom_schema
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("user_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("line_user_id", sa.String(), nullable=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("role", sa.String(), server_default="customer", nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=True),
        sa.Column("pdpa_consent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("auth_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("user_id", name="users_pkey"),
        sa.UniqueConstraint("line_user_id", name="users_line_user_id_key"),
        sa.UniqueConstraint("auth_id", name="users_auth_id_key"),
        sa.CheckConstraint("role IN ('customer', 'owner', 'rider', 'admin')", name="ck_users_role"),
    )
    op.create_table(
        "shops",
        sa.Column("shop_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("shop_name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Numeric(), nullable=True),
        sa.Column("longitude", sa.Numeric(), nullable=True),
        sa.Column("delivery_radius_km", sa.Numeric(), nullable=True),
        sa.Column("promptpay_id", sa.String(), nullable=True),
        sa.Column("is_open", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("open_time", sa.Time(), nullable=True),
        sa.Column("close_time", sa.Time(), nullable=True),
        sa.Column("min_order_amount", sa.Numeric(), server_default="0", nullable=False),
        sa.Column("delivery_fee", sa.Numeric(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("shop_id", name="shops_pkey"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.user_id"], name="shops_owner_id_fkey"),
    )
    op.create_foreign_key("fk_users_shop", "users", "shops", ["shop_id"], ["shop_id"])
    # Supabase Auth owns auth.users; this table must already exist on Supabase.
    op.create_foreign_key("users_auth_id_fkey", "users", "users", ["auth_id"], ["id"], referent_schema="auth")
    op.create_table(
        "addresses",
        sa.Column("address_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("address_text", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Numeric(), nullable=True),
        sa.Column("longitude", sa.Numeric(), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("address_id", name="addresses_pkey"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], name="addresses_user_id_fkey"),
    )
    op.create_table(
        "categories",
        sa.Column("category_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("category_name", sa.String(), nullable=False),
        sa.Column("category_group", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("category_id", name="categories_pkey"),
        sa.UniqueConstraint("category_name", name="categories_category_name_key"),
        sa.CheckConstraint("category_group IN ('อาหาร', 'ของทานเล่น', 'เครื่องดื่ม', 'ของหวาน')", name="ck_categories_category_group"),
    )
    op.create_table(
        "menus",
        sa.Column("menu_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("menu_name", sa.String(), nullable=False),
        sa.Column("price", sa.Numeric(), nullable=False),
        sa.Column("spice_level", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("is_available", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("menu_id", name="menus_pkey"),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.shop_id"], name="menus_shop_id_fkey"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.category_id"], name="menus_category_id_fkey"),
        sa.CheckConstraint("price >= 0", name="ck_menus_price"),
        sa.CheckConstraint("spice_level >= 0 AND spice_level <= 3", name="ck_menus_spice_level"),
    )
    op.create_table(
        "tags",
        sa.Column("tag_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tag_name", sa.String(), nullable=False),
        sa.Column("tag_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("proposed_by_shop_id", sa.Integer(), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("tag_id", name="tags_pkey"),
        sa.ForeignKeyConstraint(["proposed_by_shop_id"], ["shops.shop_id"], name="tags_proposed_by_shop_id_fkey"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.user_id"], name="tags_approved_by_fkey"),
        sa.CheckConstraint("tag_type IN ('taste', 'ingredient', 'cooking_method')", name="ck_tags_tag_type"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_tags_status"),
    )
    op.create_table(
        "menu_tags",
        sa.Column("menu_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("menu_id", "tag_id", name="menu_tags_pkey"),
        sa.ForeignKeyConstraint(["menu_id"], ["menus.menu_id"], name="menu_tags_menu_id_fkey"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.tag_id"], name="menu_tags_tag_id_fkey"),
    )
    op.create_table(
        "option_groups",
        sa.Column("option_group_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("menu_id", sa.Integer(), nullable=False),
        sa.Column("group_name", sa.String(), nullable=False),
        sa.Column("is_required", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("max_select", sa.SmallInteger(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("option_group_id", name="option_groups_pkey"),
        sa.ForeignKeyConstraint(["menu_id"], ["menus.menu_id"], name="option_groups_menu_id_fkey"),
        sa.CheckConstraint("max_select >= 1", name="ck_option_groups_max_select"),
    )
    op.create_table(
        "options",
        sa.Column("option_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("option_group_id", sa.Integer(), nullable=False),
        sa.Column("option_name", sa.String(), nullable=False),
        sa.Column("extra_price", sa.Numeric(), server_default="0", nullable=False),
        sa.Column("is_available", sa.Boolean(), server_default="true", nullable=False),
        sa.PrimaryKeyConstraint("option_id", name="options_pkey"),
        sa.ForeignKeyConstraint(["option_group_id"], ["option_groups.option_group_id"], name="options_option_group_id_fkey"),
        sa.CheckConstraint("extra_price >= 0", name="ck_options_extra_price"),
    )
    op.create_table(
        "orders",
        sa.Column("order_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("address_id", sa.Integer(), nullable=False),
        sa.Column("food_total", sa.Numeric(), nullable=False),
        sa.Column("delivery_fee", sa.Numeric(), server_default="0", nullable=False),
        sa.Column("total_amount", sa.Numeric(), nullable=False),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("order_id", name="orders_pkey"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], name="orders_user_id_fkey"),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.shop_id"], name="orders_shop_id_fkey"),
        sa.ForeignKeyConstraint(["address_id"], ["addresses.address_id"], name="orders_address_id_fkey"),
        sa.CheckConstraint("food_total >= 0", name="ck_orders_food_total"),
        sa.CheckConstraint("total_amount >= 0", name="ck_orders_total_amount"),
    )
    op.create_table(
        "order_items",
        sa.Column("order_item_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("menu_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("order_item_id", name="order_items_pkey"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.order_id"], name="order_items_order_id_fkey"),
        sa.ForeignKeyConstraint(["menu_id"], ["menus.menu_id"], name="order_items_menu_id_fkey"),
        sa.CheckConstraint("quantity > 0", name="ck_order_items_quantity"),
        sa.CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price"),
    )
    op.create_table(
        "order_item_options",
        sa.Column("order_item_option_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_item_id", sa.Integer(), nullable=False),
        sa.Column("option_id", sa.Integer(), nullable=True),
        sa.Column("option_name", sa.String(), nullable=False),
        sa.Column("extra_price", sa.Numeric(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("order_item_option_id", name="order_item_options_pkey"),
        sa.ForeignKeyConstraint(["order_item_id"], ["order_items.order_item_id"], name="order_item_options_order_item_id_fkey"),
        sa.ForeignKeyConstraint(["option_id"], ["options.option_id"], name="order_item_options_option_id_fkey"),
    )
    op.create_table(
        "payments",
        sa.Column("payment_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("slip_image_url", sa.String(), nullable=True),
        sa.Column("trans_ref", sa.String(), nullable=False),
        sa.Column("verify_status", sa.String(), server_default="pending", nullable=False),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("payment_id", name="payments_pkey"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.order_id"], name="payments_order_id_fkey"),
        sa.UniqueConstraint("trans_ref", name="payments_trans_ref_key"),
        sa.CheckConstraint("amount >= 0", name="ck_payments_amount"),
        sa.CheckConstraint("verify_status IN ('pending', 'passed', 'failed')", name="ck_payments_verify_status"),
    )
    op.create_table(
        "deliveries",
        sa.Column("delivery_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("rider_id", sa.Integer(), nullable=True),
        sa.Column("picked_up_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("proof_image_url", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("delivery_id", name="deliveries_pkey"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.order_id"], name="deliveries_order_id_fkey"),
        sa.ForeignKeyConstraint(["rider_id"], ["users.user_id"], name="deliveries_rider_id_fkey"),
        sa.UniqueConstraint("order_id", name="deliveries_order_id_key"),
    )
    op.create_table(
        "recommendation_logs",
        sa.Column("log_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("menu_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Numeric(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("is_ordered", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("log_id", name="recommendation_logs_pkey"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], name="recommendation_logs_user_id_fkey"),
        sa.ForeignKeyConstraint(["menu_id"], ["menus.menu_id"], name="recommendation_logs_menu_id_fkey"),
    )
    # Reference the existing Supabase Auth user table. It is not created here.
    op.create_foreign_key(
        "users_auth_id_fkey", "users", "users", ["auth_id"], ["user_id"]
    ) if False else None


def downgrade():
    op.drop_table("recommendation_logs")
    op.drop_table("deliveries")
    op.drop_table("payments")
    op.drop_table("order_item_options")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("options")
    op.drop_table("option_groups")
    op.drop_table("menu_tags")
    op.drop_table("tags")
    op.drop_table("menus")
    op.drop_table("categories")
    op.drop_table("addresses")
    op.drop_constraint("fk_users_shop", "users", type_="foreignkey")
    op.drop_table("shops")
    op.drop_table("users")
