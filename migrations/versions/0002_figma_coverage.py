"""Additive schema updates for FOM Figma workflows.

Revision ID: 0002_figma_coverage
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_figma_coverage"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    # Account moderation, consent version, and customer refund destination.
    op.add_column("users", sa.Column("account_status", sa.String(), nullable=False, server_default="active"))
    op.add_column("users", sa.Column("suspended_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("suspended_by", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("suspension_reason", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("pdpa_consent_version", sa.String(), nullable=True))
    op.add_column("users", sa.Column("refund_promptpay_id", sa.String(), nullable=True))
    op.add_column("users", sa.Column("refund_account_name", sa.String(), nullable=True))
    op.create_foreign_key("users_suspended_by_fkey", "users", "users", ["suspended_by"], ["user_id"])
    op.create_check_constraint("ck_users_account_status", "users", "account_status IN ('active', 'suspended', 'deleted')")

    # Address details shown to the delivery person.
    op.add_column("addresses", sa.Column("landmark", sa.Text(), nullable=True))
    op.add_column("addresses", sa.Column("delivery_instructions", sa.Text(), nullable=True))

    # Shop payment display and per-weekday opening hours.
    op.add_column("shops", sa.Column("promptpay_account_name", sa.String(), nullable=True))
    op.create_table(
        "shop_hours",
        sa.Column("shop_hour_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.shop_id", name="shop_hours_shop_id_fkey"), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("open_time", sa.Time(), nullable=True),
        sa.Column("close_time", sa.Time(), nullable=True),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("shop_id", "weekday", name="shop_hours_shop_weekday_key"),
        sa.CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_shop_hours_weekday"),
        sa.CheckConstraint("is_closed OR (open_time IS NOT NULL AND close_time IS NOT NULL)", name="ck_shop_hours_times"),
    )

    # Preserve status changes for order timeline and audit.
    op.create_table(
        "order_status_history",
        sa.Column("history_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.order_id", name="order_status_history_order_id_fkey"), nullable=False),
        sa.Column("old_status", sa.String(), nullable=True),
        sa.Column("new_status", sa.String(), nullable=False),
        sa.Column("changed_by", sa.Integer(), sa.ForeignKey("users.user_id", name="order_status_history_changed_by_fkey"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Payment review audit trail. Keep the existing payment row for current state.
    op.add_column("payments", sa.Column("reviewed_by", sa.Integer(), nullable=True))
    op.add_column("payments", sa.Column("review_note", sa.Text(), nullable=True))
    op.create_foreign_key("payments_reviewed_by_fkey", "payments", "users", ["reviewed_by"], ["user_id"])
    op.create_table(
        "payment_reviews",
        sa.Column("review_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.payment_id", name="payment_reviews_payment_id_fkey"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.user_id", name="payment_reviews_reviewed_by_fkey"), nullable=True),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("decision IN ('passed', 'failed', 'needs_info')", name="ck_payment_reviews_decision"),
    )

    # Refunds are separate financial transactions, not just an order status.
    op.create_table(
        "refunds",
        sa.Column("refund_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.order_id", name="refunds_order_id_fkey"), nullable=False),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.payment_id", name="refunds_payment_id_fkey"), nullable=True),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("refund_promptpay_id", sa.String(), nullable=True),
        sa.Column("refund_account_name", sa.String(), nullable=True),
        sa.Column("proof_image_url", sa.String(), nullable=True),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.user_id", name="refunds_requested_by_fkey"), nullable=True),
        sa.Column("processed_by", sa.Integer(), sa.ForeignKey("users.user_id", name="refunds_processed_by_fkey"), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount > 0", name="ck_refunds_amount"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'processing', 'completed', 'failed')", name="ck_refunds_status"),
    )

    # Privacy requests are tracked without deleting order history immediately.
    op.create_table(
        "privacy_requests",
        sa.Column("request_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id", name="privacy_requests_user_id_fkey"), nullable=False),
        sa.Column("request_type", sa.String(), nullable=False, server_default="delete"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.user_id", name="privacy_requests_reviewed_by_fkey"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('pending', 'processing', 'completed', 'rejected')", name="ck_privacy_requests_status"),
    )


def downgrade():
    op.drop_table("privacy_requests")
    op.drop_table("refunds")
    op.drop_table("payment_reviews")
    op.drop_constraint("payments_reviewed_by_fkey", "payments", type_="foreignkey")
    op.drop_column("payments", "review_note")
    op.drop_column("payments", "reviewed_by")
    op.drop_table("order_status_history")
    op.drop_table("shop_hours")
    op.drop_column("shops", "promptpay_account_name")
    op.drop_column("addresses", "delivery_instructions")
    op.drop_column("addresses", "landmark")
    op.drop_constraint("users_suspended_by_fkey", "users", type_="foreignkey")
    op.drop_constraint("ck_users_account_status", "users", type_="check")
    op.drop_column("users", "refund_account_name")
    op.drop_column("users", "refund_promptpay_id")
    op.drop_column("users", "pdpa_consent_version")
    op.drop_column("users", "suspension_reason")
    op.drop_column("users", "suspended_by")
    op.drop_column("users", "suspended_at")
    op.drop_column("users", "account_status")
