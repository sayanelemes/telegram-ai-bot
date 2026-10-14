import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user, get_productivity_repo
from app.database.models import UserDB
from app.database.repositories.productivity_repository import ProductivityRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/modes", tags=["User Modes"])


class DndRequest(BaseModel):
    hours: int = 4
    until: Optional[str] = None


class SickRequest(BaseModel):
    days: int = 3
    until: Optional[str] = None


class TravelRequest(BaseModel):
    days: int = 7
    until: Optional[str] = None


@router.get("", response_model=Dict[str, Any])
async def get_user_modes(
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """Get active modes (DND, Sick, Travel) and their expiration times."""
    return await repo.get_user_modes(user_id=current_user.id)


@router.post("/dnd", response_model=Dict[str, Any])
async def set_dnd_mode(
    payload: DndRequest,
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """Set Do Not Disturb mode until specified hour or timestamp."""
    if payload.until:
        until_iso = payload.until
    else:
        until_iso = (datetime.utcnow() + timedelta(hours=payload.hours)).isoformat()
    return await repo.set_mode(user_id=current_user.id, mode_type="dnd", until_iso=until_iso)


@router.post("/sick", response_model=Dict[str, Any])
async def set_sick_mode(
    payload: SickRequest,
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """Set Sick mode (pauses workout reminders and aggressive hunger alerts)."""
    if payload.until:
        until_iso = payload.until
    else:
        until_iso = (datetime.utcnow() + timedelta(days=payload.days)).isoformat()
    return await repo.set_mode(user_id=current_user.id, mode_type="sick", until_iso=until_iso)


@router.post("/travel", response_model=Dict[str, Any])
async def set_travel_mode(
    payload: TravelRequest,
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """Set Travel mode (pauses gym/routine check-ins)."""
    if payload.until:
        until_iso = payload.until
    else:
        until_iso = (datetime.utcnow() + timedelta(days=payload.days)).isoformat()
    return await repo.set_mode(user_id=current_user.id, mode_type="travel", until_iso=until_iso)


@router.post("/clear", response_model=Dict[str, Any])
async def clear_modes(
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """Clear all active user modes."""
    return await repo.clear_modes(user_id=current_user.id)
