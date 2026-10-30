from fastapi import APIRouter
from app.api.v1.profile import router as profile_router
from app.api.v1.shop import router as shop_router
from app.api.v1.catalog import router as catalog_router
from app.api.v1.address import router as address_router
from app.api.v1.order import router as order_router
from app.api.v1.payment import router as payment_router
from app.api.v1.delivery import router as delivery_router
from app.api.v1.admin import router as admin_router
from app.api.v1.refund import router as refund_router
from app.api.v1.privacy import router as privacy_router
router = APIRouter()
router.include_router(profile_router)
router.include_router(shop_router)
router.include_router(catalog_router)
router.include_router(address_router)
router.include_router(order_router)
router.include_router(payment_router)
router.include_router(delivery_router)
router.include_router(admin_router)
router.include_router(refund_router)
router.include_router(privacy_router)

