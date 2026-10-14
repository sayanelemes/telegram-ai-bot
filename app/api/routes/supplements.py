import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends
from app.api.deps import get_current_user, get_food_repo
from app.database.models import UserDB
from app.database.repositories import FoodRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/supplements", tags=["supplements"])


@router.get("")
async def get_supplements(
    user: UserDB = Depends(get_current_user),
    food_repo: FoodRepository = Depends(get_food_repo),
):
    return await food_repo.get_supplements(user.id)


@router.post("/check-all")
async def check_all_supplements(
    user: UserDB = Depends(get_current_user),
    food_repo: FoodRepository = Depends(get_food_repo),
):
    try:
        tz = ZoneInfo(user.timezone)
    except Exception:
        tz = ZoneInfo("Asia/Almaty")
    today_str = datetime.now(tz).strftime("%Y-%m-%d")

    await food_repo.log_supplements_taken(user.id, today_str)
    return {"success": True, "message": "Все добавки отмечены как принятые на сегодня."}
