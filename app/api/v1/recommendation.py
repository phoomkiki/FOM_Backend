from fastapi import APIRouter, Depends, Query
from app.schemas.auth import AuthUser
from app.services.auth_service import get_current_user
from app.services import recommendation_service

router = APIRouter()


@router.get('/shops/{shop_id}/recommendations', tags=['Recommendations'])
async def shop_recommendations(shop_id: int, limit: int = Query(5, ge=1, le=20), new_only: bool = False,
                               user: AuthUser = Depends(get_current_user)):
    return await recommendation_service.recommend(user.user_id, shop_id, limit, new_only)
