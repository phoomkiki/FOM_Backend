from fastapi import APIRouter, Depends, Query
from app.schemas.auth import AuthUser
from app.schemas.domain import CategoryCreate, MenuCreate, MenuUpdate, OptionCreate, OptionGroupCreate, TagCreate
from app.services.auth_service import get_current_user
from app.services import catalog_service
router = APIRouter()

@router.get('/categories', tags=['Categories'])
async def list_categories():
    return await catalog_service.list_categories()


@router.post('/categories', tags=['Categories'])
async def create_category(payload: CategoryCreate, user: AuthUser = Depends(get_current_user)):
    return await catalog_service.create_category(payload, user)


@router.patch('/categories/{category_id}', tags=['Categories'])
async def update_category(category_id: int, payload: CategoryCreate, user: AuthUser = Depends(get_current_user)):
    return await catalog_service.update_category(category_id, payload, user)


@router.delete('/categories/{category_id}', tags=['Categories'])
async def delete_category(category_id: int, user: AuthUser = Depends(get_current_user)):
    return await catalog_service.delete_category(category_id, user)


@router.get('/menus', tags=['Menus'])
async def list_menus(shop_id: int | None = None, category_id: int | None = None,
                     q: str | None = None, available_only: bool = True,
                     limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    return await catalog_service.list_menus(shop_id, category_id, q, available_only, limit, offset)


@router.post('/menus', tags=['Menus'])
async def create_menu(payload: MenuCreate, user: AuthUser = Depends(get_current_user)):
    return await catalog_service.create_menu(payload, user)


@router.get('/menus/{menu_id}', tags=['Menus'])
async def get_menu(menu_id: int):
    return await catalog_service.get_menu(menu_id)


@router.patch('/menus/{menu_id}', tags=['Menus'])
async def update_menu(menu_id: int, payload: MenuUpdate, user: AuthUser = Depends(get_current_user)):
    return await catalog_service.update_menu(menu_id, payload, user)


@router.delete('/menus/{menu_id}', tags=['Menus'])
async def delete_menu(menu_id: int, user: AuthUser = Depends(get_current_user)):
    return await catalog_service.delete_menu(menu_id, user)


@router.get('/menus/{menu_id}/options', tags=['Menu Options'])
async def list_menu_options(menu_id: int):
    return await catalog_service.list_menu_options(menu_id)


@router.post('/menus/{menu_id}/option-groups', tags=['Menu Options'])
async def create_option_group(menu_id: int, payload: OptionGroupCreate, user: AuthUser = Depends(get_current_user)):
    return await catalog_service.create_option_group(menu_id, payload, user)


@router.post('/option-groups/{group_id}/options', tags=['Menu Options'])
async def create_option(group_id: int, payload: OptionCreate, user: AuthUser = Depends(get_current_user)):
    return await catalog_service.create_option(group_id, payload, user)


@router.get('/tags', tags=['Tags'])
async def list_tags(tag_type: str | None = None):
    return await catalog_service.list_tags(tag_type)


@router.post('/tags', tags=['Tags'])
async def propose_tag(payload: TagCreate, user: AuthUser = Depends(get_current_user)):
    return await catalog_service.propose_tag(payload, user)


@router.post('/menus/{menu_id}/tags/{tag_id}', tags=['Tags'])
async def attach_tag_to_menu(menu_id: int, tag_id: int, user: AuthUser = Depends(get_current_user)):
    return await catalog_service.attach_tag_to_menu(menu_id, tag_id, user)


@router.delete('/menus/{menu_id}/tags/{tag_id}', tags=['Tags'])
async def detach_tag_from_menu(menu_id: int, tag_id: int, user: AuthUser = Depends(get_current_user)):
    return await catalog_service.detach_tag_from_menu(menu_id, tag_id, user)


