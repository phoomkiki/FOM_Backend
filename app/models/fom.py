from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()

Money = Numeric(10, 2)


def created_at_column():
    return Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    auth_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", name="users_auth_id_fkey"),
        unique=True,
    )
    line_user_id = Column(String(64), unique=True)
    display_name = Column(String(100), nullable=False)
    img_url = Column(Text)
    refund_promptpay_id = Column(String(13))
    refund_account_name = Column(String(100))
    pdpa_consent_at = Column(DateTime(timezone=True))
    pdpa_consent_version = Column(String(20))
    location_consent_at = Column(DateTime(timezone=True))
    created_at = created_at_column()


class Address(Base):
    __tablename__ = "addresses"
    __table_args__ = (
        Index("ix_addresses_user", "user_id"),
        Index(
            "ux_addresses_one_default",
            "user_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    address_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey(
            "users.user_id",
            name="addresses_user_id_fkey",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    label = Column(String(50), nullable=False)
    phone = Column(String(10), nullable=False)
    address_text = Column(Text, nullable=False)
    landmark = Column(Text)
    latitude = Column(Numeric(9, 6))
    longitude = Column(Numeric(9, 6))
    is_default = Column(Boolean, nullable=False, server_default="false")
    created_at = created_at_column()


class Shop(Base):
    __tablename__ = "shops"
    __table_args__ = (
        CheckConstraint("delivery_fee >= 0", name="ck_shops_delivery_fee"),
        CheckConstraint("min_order_amount >= 0", name="ck_shops_min_order"),
        Index("ix_shops_owner", "owner_id"),
        Index("ix_shops_location", "latitude", "longitude"),
    )

    shop_id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(
        Integer,
        ForeignKey("users.user_id", name="shops_owner_id_fkey"),
        nullable=False,
    )
    shop_name = Column(String(100), nullable=False)
    shop_type = Column(String(50))
    description = Column(String(300))
    phone = Column(String(10))
    cover_image_url = Column(Text)
    latitude = Column(Numeric(9, 6))
    longitude = Column(Numeric(9, 6))
    promptpay_id = Column(String(13))
    promptpay_account_name = Column(String(100))
    delivery_fee = Column(Money, nullable=False, server_default="0")
    min_order_amount = Column(Money, nullable=False, server_default="0")
    is_open = Column(Boolean, nullable=False, server_default="false")
    created_at = created_at_column()
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ShopHour(Base):
    __tablename__ = "shop_hours"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_shop_hours_weekday"),
        CheckConstraint(
            "is_closed OR (open_time IS NOT NULL AND close_time IS NOT NULL)",
            name="ck_shop_hours_times",
        ),
    )

    shop_id = Column(
        Integer,
        ForeignKey(
            "shops.shop_id",
            name="shop_hours_shop_id_fkey",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    weekday = Column(SmallInteger, primary_key=True)
    open_time = Column(Time)
    close_time = Column(Time)
    is_closed = Column(Boolean, nullable=False, server_default="false")


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint(
            "shop_id",
            "category_name",
            name="categories_shop_name_key",
        ),
    )

    category_id = Column(Integer, primary_key=True, autoincrement=True)
    shop_id = Column(
        Integer,
        ForeignKey(
            "shops.shop_id",
            name="categories_shop_id_fkey",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    category_name = Column(String(50), nullable=False)
    sort_order = Column(SmallInteger, nullable=False, server_default="0")


class Menu(Base):
    __tablename__ = "menus"
    __table_args__ = (
        CheckConstraint("price > 0", name="ck_menus_price"),
        Index(
            "ix_menus_shop_active",
            "shop_id",
            "category_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    menu_id = Column(Integer, primary_key=True, autoincrement=True)
    shop_id = Column(
        Integer,
        ForeignKey("shops.shop_id", name="menus_shop_id_fkey"),
        nullable=False,
    )
    category_id = Column(
        Integer,
        ForeignKey("categories.category_id", name="menus_category_id_fkey"),
        nullable=False,
    )
    menu_name = Column(String(100), nullable=False)
    price = Column(Money, nullable=False)
    description = Column(String(300))
    image_url = Column(Text)
    is_available = Column(Boolean, nullable=False, server_default="true")
    deleted_at = Column(DateTime(timezone=True))
    created_at = created_at_column()
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("tag_type", "tag_name", name="tags_type_name_key"),
        CheckConstraint(
            "tag_type IN ('taste', 'ingredient', 'cooking_method')",
            name="ck_tags_tag_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_tags_status",
        ),
        Index(
            "ix_tags_pending",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    tag_id = Column(Integer, primary_key=True, autoincrement=True)
    tag_name = Column(String(50), nullable=False)
    tag_type = Column(String(20), nullable=False)
    status = Column(String(10), nullable=False, server_default="approved")
    requested_by_shop_id = Column(
        Integer,
        ForeignKey("shops.shop_id", name="tags_requested_by_shop_id_fkey"),
    )
    requested_for_menu_id = Column(
        Integer,
        ForeignKey("menus.menu_id", name="tags_requested_for_menu_id_fkey"),
    )
    reject_reason = Column(Text)
    reviewed_at = Column(DateTime(timezone=True))
    created_at = created_at_column()


class MenuTag(Base):
    __tablename__ = "menu_tags"
    __table_args__ = (
        Index("ix_menu_tags_tag", "tag_id"),
    )

    menu_id = Column(
        Integer,
        ForeignKey(
            "menus.menu_id",
            name="menu_tags_menu_id_fkey",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    tag_id = Column(
        Integer,
        ForeignKey("tags.tag_id", name="menu_tags_tag_id_fkey"),
        primary_key=True,
    )


class OptionGroup(Base):
    __tablename__ = "option_groups"
    __table_args__ = (
        CheckConstraint("max_select >= 1", name="ck_option_groups_max_select"),
        Index("ix_option_groups_menu", "menu_id"),
    )

    option_group_id = Column(Integer, primary_key=True, autoincrement=True)
    menu_id = Column(
        Integer,
        ForeignKey(
            "menus.menu_id",
            name="option_groups_menu_id_fkey",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    group_name = Column(String(50), nullable=False)
    is_required = Column(Boolean, nullable=False, server_default="true")
    max_select = Column(SmallInteger, nullable=False, server_default="1")
    sort_order = Column(SmallInteger, nullable=False, server_default="0")


class Option(Base):
    __tablename__ = "options"
    __table_args__ = (
        CheckConstraint("extra_price >= 0", name="ck_options_extra_price"),
        Index("ix_options_group", "option_group_id"),
    )

    option_id = Column(Integer, primary_key=True, autoincrement=True)
    option_group_id = Column(
        Integer,
        ForeignKey(
            "option_groups.option_group_id",
            name="options_option_group_id_fkey",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    option_name = Column(String(50), nullable=False)
    extra_price = Column(Money, nullable=False, server_default="0")
    is_available = Column(Boolean, nullable=False, server_default="true")
    sort_order = Column(SmallInteger, nullable=False, server_default="0")


class DeliveryBatch(Base):
    __tablename__ = "delivery_batches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name="ck_delivery_batches_status",
        ),
        Index("ix_delivery_batches_shop", "shop_id", "created_at"),
    )

    batch_id = Column(Integer, primary_key=True, autoincrement=True)
    shop_id = Column(
        Integer,
        ForeignKey("shops.shop_id", name="delivery_batches_shop_id_fkey"),
        nullable=False,
    )
    batch_code = Column(String(10), nullable=False)
    qr_token = Column(String(64), nullable=False, unique=True)
    status = Column(String(10), nullable=False, server_default="active")
    scanned_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))
    created_at = created_at_column()


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_payment', 'paid', 'preparing', 'ready', "
            "'delivering', 'completed', 'cancelled')",
            name="ck_orders_status",
        ),
        CheckConstraint(
            "cancelled_by IN ('customer', 'shop', 'system')",
            name="ck_orders_cancelled_by",
        ),
        CheckConstraint("food_total >= 0", name="ck_orders_food_total"),
        CheckConstraint("delivery_fee >= 0", name="ck_orders_delivery_fee"),
        CheckConstraint(
            "total_amount = food_total + delivery_fee",
            name="ck_orders_total_amount",
        ),
        Index("ix_orders_shop_status", "shop_id", "status", "created_at"),
        Index("ix_orders_shop_created", "shop_id", "created_at"),
        Index("ix_orders_user_created", "user_id", "created_at"),
        Index("ix_orders_batch", "batch_id"),
        Index(
            "ix_orders_waiting_accept",
            "paid_at",
            postgresql_where=text("status = 'paid'"),
        ),
    )

    order_id = Column(Integer, primary_key=True, autoincrement=True)
    order_no = Column(String(10), nullable=False, unique=True)
    user_id = Column(
        Integer,
        ForeignKey("users.user_id", name="orders_user_id_fkey"),
        nullable=False,
    )
    shop_id = Column(
        Integer,
        ForeignKey("shops.shop_id", name="orders_shop_id_fkey"),
        nullable=False,
    )
    address_id = Column(
        Integer,
        ForeignKey(
            "addresses.address_id",
            name="orders_address_id_fkey",
            ondelete="SET NULL",
        ),
    )
    batch_id = Column(
        Integer,
        ForeignKey(
            "delivery_batches.batch_id",
            name="orders_batch_id_fkey",
            ondelete="SET NULL",
        ),
    )
    status = Column(String(20), nullable=False, server_default="pending_payment")
    delivery_label = Column(String(50))
    delivery_phone = Column(String(10), nullable=False)
    delivery_address_text = Column(Text, nullable=False)
    delivery_landmark = Column(Text)
    delivery_latitude = Column(Numeric(9, 6))
    delivery_longitude = Column(Numeric(9, 6))
    food_total = Column(Money, nullable=False)
    delivery_fee = Column(Money, nullable=False)
    total_amount = Column(Money, nullable=False)
    cancelled_by = Column(String(10))
    cancel_reason = Column(Text)
    paid_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))
    created_at = created_at_column()
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price"),
        CheckConstraint("line_total >= 0", name="ck_order_items_line_total"),
        Index("ix_order_items_order", "order_id"),
        Index("ix_order_items_menu", "menu_id"),
    )

    order_item_id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(
        Integer,
        ForeignKey(
            "orders.order_id",
            name="order_items_order_id_fkey",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    menu_id = Column(
        Integer,
        ForeignKey("menus.menu_id", name="order_items_menu_id_fkey"),
    )
    menu_name = Column(String(100), nullable=False)
    unit_price = Column(Money, nullable=False)
    quantity = Column(SmallInteger, nullable=False)
    line_total = Column(Money, nullable=False)
    note = Column(String(200))


class OrderItemOption(Base):
    __tablename__ = "order_item_options"
    __table_args__ = (
        Index("ix_order_item_options_item", "order_item_id"),
    )

    order_item_option_id = Column(Integer, primary_key=True, autoincrement=True)
    order_item_id = Column(
        Integer,
        ForeignKey(
            "order_items.order_item_id",
            name="order_item_options_order_item_id_fkey",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    option_id = Column(
        Integer,
        ForeignKey("options.option_id", name="order_item_options_option_id_fkey"),
    )
    option_name = Column(String(50), nullable=False)
    extra_price = Column(Money, nullable=False, server_default="0")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payments_amount"),
        CheckConstraint(
            "status IN ('waiting_slip', 'passed', 'manual_check', "
            "'manual_passed', 'manual_failed', 'expired')",
            name="ck_payments_status",
        ),
        Index(
            "ix_payments_waiting_slip",
            "qr_expires_at",
            postgresql_where=text("status = 'waiting_slip'"),
        ),
    )

    payment_id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(
        Integer,
        ForeignKey("orders.order_id", name="payments_order_id_fkey"),
        nullable=False,
        unique=True,
    )
    amount = Column(Money, nullable=False)
    qr_payload = Column(Text, nullable=False)
    qr_expires_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(15), nullable=False, server_default="waiting_slip")
    slip_image_url = Column(Text)
    trans_ref = Column(String(50), unique=True)
    payer_name = Column(String(100))
    verified_at = Column(DateTime(timezone=True))
    reviewed_by = Column(
        Integer,
        ForeignKey("users.user_id", name="payments_reviewed_by_fkey"),
    )
    created_at = created_at_column()


class Refund(Base):
    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_refunds_amount"),
        CheckConstraint(
            "status IN ('pending', 'refunded')",
            name="ck_refunds_status",
        ),
        Index(
            "ix_refunds_pending",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    refund_id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(
        Integer,
        ForeignKey("orders.order_id", name="refunds_order_id_fkey"),
        nullable=False,
        unique=True,
    )
    amount = Column(Money, nullable=False)
    promptpay_id = Column(String(13), nullable=False)
    account_name = Column(String(100))
    status = Column(String(10), nullable=False, server_default="pending")
    slip_image_url = Column(Text)
    trans_ref = Column(String(50), unique=True)
    refunded_by = Column(
        Integer,
        ForeignKey("users.user_id", name="refunds_refunded_by_fkey"),
    )
    refunded_at = Column(DateTime(timezone=True))
    created_at = created_at_column()


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        CheckConstraint(
            "proof_time_source IN ('camera', 'exif', 'upload')",
            name="ck_deliveries_proof_time_source",
        ),
        Index("ix_deliveries_batch", "batch_id"),
    )

    order_id = Column(
        Integer,
        ForeignKey("orders.order_id", name="deliveries_order_id_fkey"),
        primary_key=True,
    )
    batch_id = Column(
        Integer,
        ForeignKey("delivery_batches.batch_id", name="deliveries_batch_id_fkey"),
        nullable=False,
    )
    proof_image_url = Column(Text, nullable=False)
    proof_taken_at = Column(DateTime(timezone=True), nullable=False)
    proof_time_source = Column(String(10), nullable=False)
    delivery_note = Column(String(200))
    created_at = created_at_column()


class PrivacyRequest(Base):
    __tablename__ = "privacy_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'completed', 'rejected')",
            name="ck_privacy_requests_status",
        ),
        Index("ix_privacy_requests_user", "user_id"),
    )

    request_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey(
            "users.user_id",
            name="privacy_requests_user_id_fkey",
            ondelete="SET NULL",
        ),
    )
    status = Column(String(10), nullable=False, server_default="pending")
    reason = Column(Text)
    completed_at = Column(DateTime(timezone=True))
    created_at = created_at_column()


class OrderStatusLog(Base):
    __tablename__ = "order_status_logs"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('customer', 'shop', 'rider', 'system')",
            name="ck_order_status_logs_actor_type",
        ),
        Index("ix_order_status_logs_order", "order_id", "created_at"),
    )

    log_id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(
        Integer,
        ForeignKey(
            "orders.order_id",
            name="order_status_logs_order_id_fkey",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    from_status = Column(String(20))
    to_status = Column(String(20), nullable=False)
    actor_type = Column(String(10), nullable=False)
    actor_user_id = Column(
        Integer,
        ForeignKey(
            "users.user_id",
            name="order_status_logs_actor_user_id_fkey",
            ondelete="SET NULL",
        ),
    )
    batch_id = Column(
        Integer,
        ForeignKey("delivery_batches.batch_id", name="order_status_logs_batch_id_fkey"),
    )
    reason = Column(Text)
    created_at = created_at_column()


class SlipCheckLog(Base):
    __tablename__ = "slip_check_logs"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('payment', 'refund')",
            name="ck_slip_check_logs_purpose",
        ),
        CheckConstraint(
            "result IN ('passed', 'failed', 'error')",
            name="ck_slip_check_logs_result",
        ),
        CheckConstraint(
            "(purpose = 'payment' AND payment_id IS NOT NULL) "
            "OR (purpose = 'refund' AND refund_id IS NOT NULL)",
            name="ck_slip_check_logs_target",
        ),
        Index("ix_slip_check_logs_payment", "payment_id"),
        Index("ix_slip_check_logs_refund", "refund_id"),
        Index("ix_slip_check_logs_trans_ref", "trans_ref"),
    )

    check_id = Column(BigInteger, primary_key=True, autoincrement=True)
    purpose = Column(String(10), nullable=False)
    payment_id = Column(
        Integer,
        ForeignKey("payments.payment_id", name="slip_check_logs_payment_id_fkey"),
    )
    refund_id = Column(
        Integer,
        ForeignKey("refunds.refund_id", name="slip_check_logs_refund_id_fkey"),
    )
    slip_image_url = Column(Text, nullable=False)
    trans_ref = Column(String(50))
    slip_amount = Column(Money)
    payer_name = Column(String(100))
    receiver_account = Column(String(50))
    result = Column(String(10), nullable=False)
    fail_reason = Column(String(50))
    api_response = Column(JSONB)
    created_at = created_at_column()


class ActivityLog(Base):
    __tablename__ = "activity_logs"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('customer', 'shop', 'rider', 'system')",
            name="ck_activity_logs_actor_type",
        ),
        Index("ix_activity_logs_shop", "shop_id", "created_at"),
        Index("ix_activity_logs_user", "actor_user_id", "created_at"),
        Index("ix_activity_logs_entity", "entity_type", "entity_id"),
        Index(
            "ix_activity_logs_created_brin",
            "created_at",
            postgresql_using="brin",
        ),
    )

    log_id = Column(BigInteger, primary_key=True, autoincrement=True)
    actor_type = Column(String(10), nullable=False)
    actor_user_id = Column(
        Integer,
        ForeignKey(
            "users.user_id",
            name="activity_logs_actor_user_id_fkey",
            ondelete="SET NULL",
        ),
    )
    shop_id = Column(
        Integer,
        ForeignKey(
            "shops.shop_id",
            name="activity_logs_shop_id_fkey",
            ondelete="SET NULL",
        ),
    )
    action = Column(String(50), nullable=False)
    entity_type = Column(String(30), nullable=False)
    entity_id = Column(Integer)
    old_data = Column(JSONB)
    new_data = Column(JSONB)
    created_at = created_at_column()


class NotificationLog(Base):
    __tablename__ = "notification_logs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('sent', 'failed')",
            name="ck_notification_logs_status",
        ),
        Index("ix_notification_logs_order", "order_id"),
    )

    log_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey(
            "users.user_id",
            name="notification_logs_user_id_fkey",
            ondelete="SET NULL",
        ),
    )
    order_id = Column(
        Integer,
        ForeignKey(
            "orders.order_id",
            name="notification_logs_order_id_fkey",
            ondelete="CASCADE",
        ),
    )
    template = Column(String(50), nullable=False)
    status = Column(String(10), nullable=False)
    error_message = Column(Text)
    created_at = created_at_column()


class RecommendationLog(Base):
    __tablename__ = "recommendation_logs"
    __table_args__ = (
        Index("ix_recommendation_logs_user", "user_id", "created_at"),
        Index("ix_recommendation_logs_shop", "shop_id", "created_at"),
    )

    log_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey(
            "users.user_id",
            name="recommendation_logs_user_id_fkey",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    shop_id = Column(
        Integer,
        ForeignKey("shops.shop_id", name="recommendation_logs_shop_id_fkey"),
        nullable=False,
    )
    menu_id = Column(
        Integer,
        ForeignKey("menus.menu_id", name="recommendation_logs_menu_id_fkey"),
        nullable=False,
    )
    score = Column(Numeric(6, 5), nullable=False)
    rank = Column(SmallInteger, nullable=False)
    is_ordered = Column(Boolean, nullable=False, server_default="false")
    order_id = Column(
        Integer,
        ForeignKey("orders.order_id", name="recommendation_logs_order_id_fkey"),
    )
    created_at = created_at_column()