from fastapi import APIRouter, Depends
from app.schemas.auth import AuthUser
from app.schemas.domain import RefundCreate, RefundReview
from app.services.auth_service import get_current_user
from app.services import refund_service
router = APIRouter()

@router.post('/orders/{order_id}/refunds', tags=['Refunds'])
async def request_refund(order_id: int, payload: RefundCreate, user: AuthUser = Depends(get_current_user)):
    return await refund_service.create_refund(order_id, payload, user)


@router.get('/refunds/mine', tags=['Refunds'])
async def get_my_refunds(user: AuthUser = Depends(get_current_user)):
    return await refund_service.my_refunds(user)


@router.get('/admin/refunds', tags=['Admin - Refunds'])
async def get_admin_refunds(status_filter: str | None = None, user: AuthUser = Depends(get_current_user)):
    return await refund_service.admin_refunds(status_filter, user)


@router.patch('/admin/refunds/{refund_id}/review', tags=['Admin - Refunds'])
async def review_refund(refund_id: int, payload: RefundReview, user: AuthUser = Depends(get_current_user)):
    return await refund_service.admin_review_refund(refund_id, payload, user)


