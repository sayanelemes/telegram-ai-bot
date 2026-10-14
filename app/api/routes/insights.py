import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_insights_service, get_insights_repo
from app.database.models import UserDB
from app.database.repositories.insights_repository import InsightsRepository
from app.services.insights import InsightsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/insights", tags=["Insights & Auditor"])


class ApplyAdviceRequest(BaseModel):
    card_index: int = Field(0, ge=0, le=2)


@router.get("/audit", response_model=Dict[str, Any])
async def get_insights_audit(
    current_user: UserDB = Depends(get_current_user),
    service: InsightsService = Depends(get_insights_service),
):
    """
    Run 5 deterministic bulking detectors without Gemini.
    If less than 14 days of data, returns 'insufficient_data'.
    """
    return await service.audit_user(user_id=current_user.id)


@router.get("/advice", response_model=Dict[str, Any])
async def get_latest_advice(
    current_user: UserDB = Depends(get_current_user),
    repo: InsightsRepository = Depends(get_insights_repo),
    service: InsightsService = Depends(get_insights_service),
):
    """
    Get latest weekly advice cards, or generate if none exists.
    """
    latest = await repo.get_latest_ai_advice(user_id=current_user.id)
    if latest:
        return latest
    return await service.generate_weekly_advice(user_id=current_user.id)


@router.post("/advice/generate", response_model=Dict[str, Any])
async def generate_advice(
    current_user: UserDB = Depends(get_current_user),
    service: InsightsService = Depends(get_insights_service),
):
    """
    Force generate new weekly advice (calls Gemini structured output with findings).
    """
    return await service.generate_weekly_advice(user_id=current_user.id)


@router.post("/advice/{advice_id}/apply", response_model=Dict[str, Any])
async def apply_advice(
    advice_id: int,
    payload: ApplyAdviceRequest,
    current_user: UserDB = Depends(get_current_user),
    service: InsightsService = Depends(get_insights_service),
):
    """
    Apply action from one of the advice cards (e.g. raise calorie target, schedule snack reminder, add shake).
    """
    try:
        return await service.apply_advice_action(
            user_id=current_user.id,
            advice_id=advice_id,
            card_index=payload.card_index,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/advice/{advice_id}/undo", response_model=Dict[str, Any])
async def undo_advice(
    advice_id: int,
    current_user: UserDB = Depends(get_current_user),
    service: InsightsService = Depends(get_insights_service),
):
    """
    Undo previously applied advice action.
    """
    try:
        return await service.undo_advice_action(
            user_id=current_user.id,
            advice_id=advice_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/advice/{advice_id}/evaluate", response_model=Dict[str, Any])
async def evaluate_advice(
    advice_id: int,
    current_user: UserDB = Depends(get_current_user),
    service: InsightsService = Depends(get_insights_service),
):
    """
    Check 2-week effectiveness of applied advice.
    """
    result = await service.evaluate_advice_effect(advice_id=advice_id)
    if not result:
        raise HTTPException(status_code=404, detail="Advice not found")
    return result
