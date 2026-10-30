from fastapi import APIRouter, Depends
from app.schemas.auth import AuthUser
from app.schemas.domain import PaymentCreate, SlipSubmit, PaymentReview
from app.services.auth_service import get_current_user
from app.services import payment_service

router = APIRouter()

@router.post('/payments', status_code=201, tags=['Payments'])
async def create_payment(payload: PaymentCreate, user: AuthUser = Depends(get_current_user)):
    return await payment_service.create_payment(payload, user)

@router.post('/payments/{payment_id}/slip', tags=['Payments'])
async def submit_payment_slip(payment_id: int, payload: SlipSubmit, user: AuthUser = Depends(get_current_user)):
    return await payment_service.submit_payment_slip(payment_id, payload, user)

@router.get('/payments/mine', tags=['Payments'])
async def my_payments(user: AuthUser = Depends(get_current_user)):
    return await payment_service.my_payments(user)

@router.get('/admin/payments', tags=['Admin - Payments'])
async def admin_payments(verify_status: str | None = None, user: AuthUser = Depends(get_current_user)):
    return await payment_service.admin_payments(verify_status, user)

@router.patch('/admin/payments/{payment_id}/review', tags=['Admin - Payments'])
async def admin_review_payment(payment_id: int, payload: PaymentReview, user: AuthUser = Depends(get_current_user)):
    return await payment_service.admin_review_payment(payment_id, payload, user)
