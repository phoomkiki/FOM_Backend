from fastapi import APIRouter, Depends, Query
from app.schemas.auth import AuthUser
from app.schemas.domain import ShopCreate, ShopUpdate, ShopHourInput
from app.services.auth_service import get_current_user
from app.services import shop_service
router = APIRouter()

@router.get('/shops', tags=['Shops'])
async def list_shops(q: str | None = None, category_id: int | None = None,
                     limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return await shop_service.list_shops(q, category_id, limit, offset)


@router.get('/shops/mine', tags=['Shops'])
async def my_shops(user: AuthUser = Depends(get_current_user)):
    return await shop_service.my_shops(user)


@router.post('/shops', tags=['Shops'])
async def create_shop(payload: ShopCreate, user: AuthUser = Depends(get_current_user)):
    # Customer can apply to become a shop owner; the shop remains pending until admin approval.
    return await shop_service.create_shop(payload, user)


@router.get('/shops/{shop_id}', tags=['Shops'])
async def get_shop(shop_id: int):
    return await shop_service.get_shop(shop_id)


@router.patch('/shops/{shop_id}', tags=['Shops'])
async def update_shop(shop_id: int, payload: ShopUpdate, user: AuthUser = Depends(get_current_user)):
    return await shop_service.update_shop(shop_id, payload, user)


@router.get('/shops/{shop_id}/hours', tags=['Shops'])
async def get_shop_hours(shop_id: int):
    return await shop_service.list_shop_hours(shop_id)


@router.put('/shops/{shop_id}/hours', tags=['Shops'])
async def put_shop_hours(shop_id: int, payload: ShopHourInput, user: AuthUser = Depends(get_current_user)):
    return await shop_service.upsert_shop_hour(shop_id, payload, user)



@router.get('/shops/{shop_id}/orders', tags=['Shop Orders'])
async def shop_orders(shop_id: int, status_filter: str | None = None, limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0), user: AuthUser = Depends(get_current_user)):
    return await shop_service.shop_orders(shop_id, status_filter, limit, offset, user)
