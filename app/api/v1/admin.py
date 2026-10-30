from fastapi import APIRouter, Depends, Query
from app.schemas.auth import AuthUser
from app.schemas.domain import AdminRoleUpdate, ShopApproval, TagReview
from app.services.auth_service import get_current_user
from app.services import admin_service

router = APIRouter()

@router.get('/admin/overview', tags=['Admin'])
async def admin_overview(user: AuthUser = Depends(get_current_user)):
    return await admin_service.admin_overview(user)

@router.get('/admin/users', tags=['Admin - Users'])
async def admin_users(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), user: AuthUser = Depends(get_current_user)):
    return await admin_service.admin_users(limit, offset, user)

@router.patch('/admin/users/{user_id}/role', tags=['Admin - Users'])
async def admin_update_role(user_id: int, payload: AdminRoleUpdate, user: AuthUser = Depends(get_current_user)):
    return await admin_service.admin_update_role(user_id, payload, user)

@router.get('/admin/shops', tags=['Admin - Shops'])
async def admin_shops(user: AuthUser = Depends(get_current_user)):
    return await admin_service.admin_shops(user)

@router.patch('/admin/shops/{shop_id}/approval', tags=['Admin - Shops'])
async def admin_shop_approval(shop_id: int, payload: ShopApproval, user: AuthUser = Depends(get_current_user)):
    return await admin_service.admin_shop_approval(shop_id, payload, user)

@router.get('/admin/orders', tags=['Admin - Orders'])
async def admin_orders(status_filter: str | None = None, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), user: AuthUser = Depends(get_current_user)):
    return await admin_service.admin_orders(status_filter, limit, offset, user)

@router.get('/admin/deliveries', tags=['Admin - Delivery'])
async def admin_deliveries(user: AuthUser = Depends(get_current_user)):
    return await admin_service.admin_deliveries(user)

@router.get('/admin/tags', tags=['Admin - Tags'])
async def admin_tags(status_filter: str | None = None, user: AuthUser = Depends(get_current_user)):
    return await admin_service.admin_tags(status_filter, user)

@router.patch('/admin/tags/{tag_id}/review', tags=['Admin - Tags'])
async def admin_review_tag(tag_id: int, payload: TagReview, user: AuthUser = Depends(get_current_user)):
    return await admin_service.admin_review_tag(tag_id, payload, user)

@router.get('/admin/delivery-batches', tags=['Admin - Delivery'])
async def admin_delivery_batches(user: AuthUser = Depends(get_current_user)):
    return await admin_service.admin_delivery_batches(user)

@router.delete('/admin/delivery-batches/{batch_id}', tags=['Admin - Delivery'])
async def admin_revoke_batch(batch_id: int, user: AuthUser = Depends(get_current_user)):
    return await admin_service.admin_revoke_batch(batch_id, user)
