from fastapi import APIRouter, Depends
from app.schemas.auth import AuthUser
from app.schemas.domain import PrivacyRequestCreate, PrivacyRequestReview
from app.services.auth_service import get_current_user
from app.services import privacy_service
router = APIRouter()

@router.post('/privacy-requests', tags=['Privacy'])
async def request_privacy_action(payload: PrivacyRequestCreate, user: AuthUser = Depends(get_current_user)):
    return await privacy_service.create_privacy_request(payload, user)


@router.get('/privacy-requests/mine', tags=['Privacy'])
async def get_my_privacy_requests(user: AuthUser = Depends(get_current_user)):
    return await privacy_service.my_privacy_requests(user)


@router.get('/admin/privacy-requests', tags=['Admin - Privacy'])
async def get_admin_privacy_requests(status_filter: str | None = None, user: AuthUser = Depends(get_current_user)):
    return await privacy_service.admin_privacy_requests(status_filter, user)


@router.patch('/admin/privacy-requests/{request_id}/review', tags=['Admin - Privacy'])
async def review_privacy_request(request_id: int, payload: PrivacyRequestReview, user: AuthUser = Depends(get_current_user)):
    return await privacy_service.admin_review_privacy_request(request_id, payload, user)


