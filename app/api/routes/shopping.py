import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_recipe_service
from app.database.models import UserDB
from app.services.recipes import RecipeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shopping-list", tags=["shopping"])


class ShoppingItemCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    amount_str: Optional[str] = None
    category: str = "food"


class ShoppingItemUpdateRequest(BaseModel):
    is_bought: Optional[bool] = None
    bought_price: Optional[float] = None


class FromRecipeRequest(BaseModel):
    recipe_data: Optional[Dict[str, Any]] = None


@router.get("")
async def get_shopping_list(
    user: UserDB = Depends(get_current_user),
    recipe_service: RecipeService = Depends(get_recipe_service),
):
    items = await recipe_service.get_shopping_items(user.id)
    return items


@router.post("")
async def add_shopping_item(
    payload: ShoppingItemCreateRequest,
    user: UserDB = Depends(get_current_user),
    recipe_service: RecipeService = Depends(get_recipe_service),
):
    item = await recipe_service.add_shopping_item(
        user_id=user.id,
        name=payload.name,
        amount_str=payload.amount_str,
        category=payload.category,
    )
    return item


@router.patch("/{item_id}")
async def toggle_shopping_item(
    item_id: int,
    payload: ShoppingItemUpdateRequest,
    user: UserDB = Depends(get_current_user),
    recipe_service: RecipeService = Depends(get_recipe_service),
):
    updated = await recipe_service.toggle_shopping_item(
        user_id=user.id,
        item_id=item_id,
        is_bought=payload.is_bought,
        bought_price=payload.bought_price,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден.")
    return updated


@router.delete("/cleared")
async def clear_bought_items(
    user: UserDB = Depends(get_current_user),
    recipe_service: RecipeService = Depends(get_recipe_service),
):
    count = await recipe_service.clear_bought_items(user.id)
    return {"success": True, "cleared_count": count}


@router.delete("/{item_id}")
async def delete_shopping_item(
    item_id: int,
    user: UserDB = Depends(get_current_user),
    recipe_service: RecipeService = Depends(get_recipe_service),
):
    deleted = await recipe_service.delete_shopping_item(user.id, item_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден.")
    return {"success": True, "message": "Товар удалён из списка покупок"}


@router.post("/from-recipe")
async def add_from_recipe(
    payload: FromRecipeRequest,
    user: UserDB = Depends(get_current_user),
    recipe_service: RecipeService = Depends(get_recipe_service),
):
    try:
        added = await recipe_service.add_recipe_to_shopping_list(user.id, payload.recipe_data)
        return {"success": True, "added": added, "count": len(added)}
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.post("/import-weekly-plan")
async def import_weekly_plan(
    user: UserDB = Depends(get_current_user),
    recipe_service: RecipeService = Depends(get_recipe_service),
):
    try:
        count = await recipe_service.import_weekly_plan_to_shopping_list(user.id)
        return {"success": True, "imported_count": count}
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
