import logging
from datetime import datetime
from typing import List, Dict, Any
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user, get_productivity_repo
from app.database.models import UserDB
from app.database.repositories.productivity_repository import ProductivityRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/habits", tags=["Habits"])


class HabitCreateRequest(BaseModel):
    name: str
    target_frequency: str = "daily"


@router.get("", response_model=List[Dict[str, Any]])
async def get_habits(
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """List habits with current completion status for today and streak counters."""
    tz_str = current_user.timezone or "Asia/Almaty"
    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        tz = ZoneInfo("Asia/Almaty")
    today_str = datetime.now(tz=tz).date().isoformat()

    return await repo.get_habits_with_status(user_id=current_user.id, target_date=today_str)


@router.post("", response_model=Dict[str, Any])
async def create_habit(
    payload: HabitCreateRequest,
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """Create a new habit."""
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    return await repo.create_habit(
        user_id=current_user.id,
        name=payload.name,
        target_frequency=payload.target_frequency,
    )


@router.post("/{habit_id}/toggle", response_model=Dict[str, Any])
async def toggle_habit(
    habit_id: int,
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """Toggle habit completion for today. Automatically maintains streaks."""
    tz_str = current_user.timezone or "Asia/Almaty"
    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        tz = ZoneInfo("Asia/Almaty")
    today_str = datetime.now(tz=tz).date().isoformat()

    result = await repo.toggle_habit_log(user_id=current_user.id, habit_id=habit_id, log_date=today_str)
    return result


@router.get("/threats", response_model=List[Dict[str, Any]])
async def get_habit_threats(
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """Get pending habits for today that threaten to break streak."""
    tz_str = current_user.timezone or "Asia/Almaty"
    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        tz = ZoneInfo("Asia/Almaty")
    today_str = datetime.now(tz=tz).date().isoformat()

    return await repo.get_pending_habits_for_today(user_id=current_user.id, log_date=today_str)


@router.delete("/{habit_id}")
async def delete_habit(
    habit_id: int,
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """Delete habit."""
    deleted = await repo.delete_habit(user_id=current_user.id, habit_id=habit_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Habit not found")
    return {"status": "ok", "deleted_id": habit_id}
