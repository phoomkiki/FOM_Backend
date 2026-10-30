from fastapi import APIRouter, Depends
from app.schemas.auth import AuthUser
from app.schemas.domain import AddressCreate
from app.services.auth_service import get_current_user
from app.services import address_service
router = APIRouter()

@router.get('/addresses', tags=['Addresses'])
async def list_addresses(user: AuthUser = Depends(get_current_user)):
    return await address_service.list_addresses(user)


@router.post('/addresses', tags=['Addresses'])
async def create_address(payload: AddressCreate, user: AuthUser = Depends(get_current_user)):
    return await address_service.create_address(payload, user)


@router.patch('/addresses/{address_id}', tags=['Addresses'])
async def update_address(address_id: int, payload: AddressCreate, user: AuthUser = Depends(get_current_user)):
    return await address_service.update_address(address_id, payload, user)


@router.delete('/addresses/{address_id}', tags=['Addresses'])
async def delete_address(address_id: int, user: AuthUser = Depends(get_current_user)):
    return await address_service.delete_address(address_id, user)


