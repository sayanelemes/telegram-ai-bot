import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user, get_food_repo
from app.database.models import UserDB
from app.database.repositories import FoodRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pantry", tags=["pantry"])


class PantryItemCreateRequest(BaseModel):
    name: str
    amount_str: Optional[str] = None


class PantryFromReceiptRequest(BaseModel):
    items: List[str]


@router.get("")
async def list_pantry_items(
    user: UserDB = Depends(get_current_user),
    food_repo: FoodRepository = Depends(get_food_repo),
):
    return await food_repo.get_pantry_items(user.id)


@router.post("")
async def add_pantry_item(
    payload: PantryItemCreateRequest,
    user: UserDB = Depends(get_current_user),
    food_repo: FoodRepository = Depends(get_food_repo),
):
    item_id = await food_repo.add_pantry_item(
        user_id=user.id,
        name=payload.name,
        amount_str=payload.amount_str
    )
    return {"id": item_id, "name": payload.name, "success": True}


@router.post("/from-receipt")
async def add_pantry_from_receipt(
    payload: PantryFromReceiptRequest,
    user: UserDB = Depends(get_current_user),
    food_repo: FoodRepository = Depends(get_food_repo),
):
    """Adds purchased products from store receipt into home pantry."""
    added = []
    for item_name in payload.items:
        if item_name.strip():
            item_id = await food_repo.add_pantry_item(user_id=user.id, name=item_name.strip())
            added.append({"id": item_id, "name": item_name.strip()})
    return {"success": True, "added_count": len(added), "items": added}


@router.delete("/{pantry_id}")
async def delete_pantry_item(
    pantry_id: int,
    user: UserDB = Depends(get_current_user),
    food_repo: FoodRepository = Depends(get_food_repo),
):
    success = await food_repo.delete_pantry_item(pantry_id, user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Элемент кладовой не найден.")
    return {"success": True}
