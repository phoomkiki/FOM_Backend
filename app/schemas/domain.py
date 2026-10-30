from datetime import time
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field

class RefundAccountUpdate(BaseModel):
    refund_promptpay_id: str | None = Field(default=None, min_length=8, max_length=13)
    refund_account_name: str | None = Field(default=None, min_length=1, max_length=100)

class ProfileAddressUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=50)
    phone: str | None = Field(default=None, min_length=8, max_length=10)
    address_text: str | None = Field(default=None, min_length=5, max_length=2000)
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    is_default: bool | None = None
    landmark: str | None = Field(default=None, max_length=2000)

class PdpaConsentUpdate(BaseModel):
    pdpa_consent: Literal[True]
    pdpa_consent_version: str = Field(min_length=1, max_length=20)

class ShopCreate(BaseModel):
    shop_name: str = Field(min_length=2, max_length=100)
    shop_type: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, min_length=8, max_length=10)
    cover_image_url: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    promptpay_id: str | None = Field(default=None, max_length=13)
    promptpay_account_name: str | None = Field(default=None, max_length=100)
    min_order_amount: Decimal = Field(default=Decimal("0"), ge=0)
    delivery_fee: Decimal = Field(default=Decimal("0"), ge=0)

class ShopUpdate(BaseModel):
    shop_name: str | None = Field(default=None, min_length=2, max_length=100)
    shop_type: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, min_length=8, max_length=10)
    cover_image_url: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    promptpay_id: str | None = Field(default=None, max_length=13)
    promptpay_account_name: str | None = Field(default=None, max_length=100)
    is_open: bool | None = None
    min_order_amount: Decimal | None = Field(default=None, ge=0)
    delivery_fee: Decimal | None = Field(default=None, ge=0)

class CategoryCreate(BaseModel):
    shop_id: int
    category_name: str = Field(min_length=1, max_length=50)
    sort_order: int = Field(default=0, ge=0, le=32767)

class MenuCreate(BaseModel):
    shop_id: int
    category_id: int
    menu_name: str = Field(min_length=1, max_length=100)
    price: Decimal = Field(gt=0)
    description: str | None = Field(default=None, max_length=300)
    image_url: str | None = None
    is_available: bool = True

class MenuUpdate(BaseModel):
    category_id: int | None = None
    menu_name: str | None = Field(default=None, min_length=1, max_length=100)
    price: Decimal | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=300)
    image_url: str | None = None
    is_available: bool | None = None

class TagCreate(BaseModel):
    tag_name: str = Field(min_length=1, max_length=50)
    tag_type: str

class OptionGroupCreate(BaseModel):
    group_name: str = Field(min_length=1, max_length=50)
    is_required: bool = True
    max_select: int = Field(default=1, ge=1, le=32767)
    sort_order: int = Field(default=0, ge=0, le=32767)

class OptionCreate(BaseModel):
    option_name: str = Field(min_length=1, max_length=50)
    extra_price: Decimal = Field(default=Decimal("0"), ge=0)
    is_available: bool = True
    sort_order: int = Field(default=0, ge=0, le=32767)

class AddressCreate(BaseModel):
    label: str = Field(min_length=1, max_length=50)
    phone: str = Field(min_length=8, max_length=10)
    address_text: str = Field(min_length=5, max_length=2000)
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    is_default: bool = False
    landmark: str | None = Field(default=None, max_length=2000)

class OrderItemInput(BaseModel):
    menu_id: int
    quantity: int = Field(ge=1, le=99)
    option_ids: list[int] = Field(default_factory=list, max_length=30)
    note: str | None = Field(default=None, max_length=200)

class OrderCreate(BaseModel):
    shop_id: int
    address_id: int
    items: list[OrderItemInput] = Field(min_length=1, max_length=50)
    note: str | None = Field(default=None, max_length=1000)

class OrderStatusUpdate(BaseModel):
    status: str

class PaymentCreate(BaseModel):
    order_id: int

class PaymentReview(BaseModel):
    verify_status: str
    note: str | None = None

class SlipSubmit(BaseModel):
    slip_image_url: str = Field(min_length=8, max_length=2000)

class DeliveryBatchCreate(BaseModel):
    order_ids: list[int] = Field(min_length=1, max_length=50)
    expires_in_minutes: int = Field(default=120, ge=5, le=720)

class DeliveryClaim(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=8, max_length=10)

class DeliveryComplete(BaseModel):
    proof_image_url: str = Field(min_length=8, max_length=2000)
    delivery_note: str | None = Field(default=None, max_length=200)

class AdminRoleUpdate(BaseModel):
    role: str

class ShopApproval(BaseModel):
    approval_status: str
    reject_reason: str | None = None

class TagReview(BaseModel):
    status: str
    reject_reason: str | None = None

class ShopHourInput(BaseModel):
    weekday: int = Field(ge=0, le=6)
    open_time: time | None = None
    close_time: time | None = None
    is_closed: bool = False

class RefundCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    reason: str = Field(min_length=3, max_length=1000)
    refund_promptpay_id: str | None = Field(default=None, max_length=13)
    refund_account_name: str | None = Field(default=None, max_length=100)

class RefundReview(BaseModel):
    status: str
    admin_note: str | None = Field(default=None, max_length=1000)

class PrivacyRequestCreate(BaseModel):
    request_type: str = "delete"
    reason: str | None = Field(default=None, max_length=1000)

class PrivacyRequestReview(BaseModel):
    status: str
    reason: str | None = Field(default=None, max_length=1000)
