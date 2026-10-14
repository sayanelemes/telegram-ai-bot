import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query
from app.api.deps import get_current_user, get_stats_service
from app.api.schemas import (
    NutritionStatsResponse,
    ExpenseStatsResponse,
    WeeklySummaryResponse,
)
from app.database.models import UserDB
from app.services.stats import StatsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/nutrition", response_model=NutritionStatsResponse)
async def get_nutrition_stats(
    period: str = Query("week", description="Period: day | week | month"),
    user: UserDB = Depends(get_current_user),
    stats_service: StatsService = Depends(get_stats_service),
):
    stats = await stats_service.get_nutrition_stats(
        user_id=user.id,
        period=period,
        timezone_str=user.timezone,
    )
    return NutritionStatsResponse(**stats)


@router.get("/expenses", response_model=ExpenseStatsResponse)
async def get_expense_stats(
    period: str = Query("month", description="Period: day | week | month"),
    user: UserDB = Depends(get_current_user),
    stats_service: StatsService = Depends(get_stats_service),
):
    stats = await stats_service.get_expense_stats(
        user_id=user.id,
        period=period,
        timezone_str=user.timezone,
    )
    return ExpenseStatsResponse(**stats)


@router.get("/weekly-summary", response_model=WeeklySummaryResponse)
async def get_weekly_summary(
    user: UserDB = Depends(get_current_user),
    stats_service: StatsService = Depends(get_stats_service),
):
    summary = await stats_service.generate_weekly_summary(
        user_id=user.id,
        timezone_str=user.timezone,
    )
    return WeeklySummaryResponse(**summary)
