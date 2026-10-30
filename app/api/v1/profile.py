from fastapi import APIRouter, Depends, HTTPException
from app.schemas.auth import AuthUser
from app.schemas.domain import PdpaConsentUpdate, ProfileAddressUpdate, RefundAccountUpdate
from app.services.auth_service import get_current_user
from app.services import profile_service

router = APIRouter()


@router.get('/profile/me', tags=['Profile'])
async def profile_me(user: AuthUser = Depends(get_current_user)):
    return await profile_service.profile_me(user)


@router.patch('/profile/refund-account', tags=['Profile'])
async def update_refund_account(payload: RefundAccountUpdate, user: AuthUser = Depends(get_current_user)):
    return await profile_service.update_refund_account(payload, user)


@router.patch('/profile/addresses/{address_id}', tags=['Profile'])
async def update_profile_address(address_id: int, payload: ProfileAddressUpdate, user: AuthUser = Depends(get_current_user)):
    return await profile_service.update_profile_address(address_id, payload, user)


@router.patch('/profile/pdpa-consent', tags=['Profile'])
async def update_pdpa_consent(payload: PdpaConsentUpdate, user: AuthUser = Depends(get_current_user)):
    if payload.pdpa_consent is not True:
        raise HTTPException(422, 'pdpa_consent must be true.')
    return await profile_service.update_pdpa_consent(payload, user)
