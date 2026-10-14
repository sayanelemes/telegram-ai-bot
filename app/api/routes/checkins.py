import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_current_user, get_productivity_repo
from app.database.models import UserDB
from app.database.repositories.productivity_repository import ProductivityRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/checkins", tags=["Check-ins"])


class CheckInRequest(BaseModel):
    mood: int  # 1-5
    energy: int  # 1-5
    satiety: int = 3  # 1-5 (сытость)
    notes: Optional[str] = None
    log_date: Optional[str] = None


@router.post("", response_model=Dict[str, Any])
async def submit_check_in(
    payload: CheckInRequest,
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """Save or update evening check-in (mood, energy, satiety 1-5)."""
    if not (1 <= payload.mood <= 5 and 1 <= payload.energy <= 5 and 1 <= payload.satiety <= 5):
        raise HTTPException(status_code=400, detail="Ratings must be between 1 and 5")

    tz_str = current_user.timezone or "Asia/Almaty"
    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        tz = ZoneInfo("Asia/Almaty")
    target_date = payload.log_date or datetime.now(tz=tz).date().isoformat()

    return await repo.save_check_in(
        user_id=current_user.id,
        log_date=target_date,
        mood=payload.mood,
        energy=payload.energy,
        satiety=payload.satiety,
        notes=payload.notes,
    )


@router.get("/today", response_model=Optional[Dict[str, Any]])
async def get_today_check_in(
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """Get today's check-in if submitted."""
    tz_str = current_user.timezone or "Asia/Almaty"
    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        tz = ZoneInfo("Asia/Almaty")
    today_str = datetime.now(tz=tz).date().isoformat()

    return await repo.get_today_check_in(user_id=current_user.id, target_date=today_str)


@router.get("/history", response_model=List[Dict[str, Any]])
async def get_check_in_history(
    limit: int = Query(7, ge=1, le=90),
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """Get past check-ins history."""
    return await repo.get_check_in_history(user_id=current_user.id, limit=limit)
