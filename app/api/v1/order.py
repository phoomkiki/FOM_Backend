from fastapi import APIRouter, Depends, Query
from app.schemas.auth import AuthUser
from app.schemas.domain import OrderCreate, OrderStatusUpdate
from app.services.auth_service import get_current_user
from app.services import order_service
router = APIRouter()
@router.post('/orders', status_code=201, tags=['Orders'])
async def create_order(payload: OrderCreate, user: AuthUser = Depends(get_current_user)):
    return await order_service.create_order(payload, user)
@router.get('/orders/mine', tags=['Orders'])
async def my_orders(status_filter: str | None = None, limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0), user: AuthUser = Depends(get_current_user)):
    return await order_service.my_orders(status_filter, limit, offset, user)
@router.get('/orders/{order_id}', tags=['Orders'])
async def get_order(order_id: int, user: AuthUser = Depends(get_current_user)):
    return await order_service.get_order(order_id, user)
@router.patch('/orders/{order_id}/status', tags=['Orders'])
async def update_order_status(order_id: int, payload: OrderStatusUpdate, user: AuthUser = Depends(get_current_user)):
    return await order_service.update_order_status(order_id, payload, user)
