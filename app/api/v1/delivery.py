from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.schemas.auth import AuthUser
from app.schemas.domain import DeliveryBatchCreate, DeliveryClaim, DeliveryComplete
from app.services.auth_service import get_current_user
from app.services import delivery_service
router = APIRouter()

@router.post('/delivery-batches', tags=['Delivery'])
async def create_delivery_batch(payload: DeliveryBatchCreate, user: AuthUser = Depends(get_current_user)):
    return await delivery_service.create_delivery_batch(payload, user)


@router.get('/delivery-batches/scan', tags=['Delivery'])
async def scan_delivery_batch(token: str):
    return await delivery_service.scan_delivery_batch(token)


@router.post('/delivery-batches/claim', tags=['Delivery'])
async def claim_delivery_batch(token: str, payload: DeliveryClaim):
    return await delivery_service.claim_delivery_batch(token, payload)


@router.post('/deliveries/{order_id}/complete', tags=['Delivery'])
async def complete_delivery(order_id: int, payload: DeliveryComplete,
                            credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    return await delivery_service.complete_delivery(order_id, payload, credentials)


