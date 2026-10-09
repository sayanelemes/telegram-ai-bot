from typing import List
from fastapi import APIRouter, Depends, Query, HTTPException, status
from app.api.deps import (
    get_current_user,
    get_user_repo,
    get_food_repo,
)
from app.api.schemas import (
    HistoryDayResponse,
    FoodEntryResponse,
    FoodItemSchema,
)
from app.database.models import UserDB
from app.database.repositories import UserRepository, FoodRepository

router = APIRouter(prefix="/history", tags=["history"])


@router.get("", response_model=List[HistoryDayResponse])
async def get_history(
    limit: int = Query(default=14, ge=1, le=60),
    offset: int = Query(default=0, ge=0),
    user: UserDB = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repo),
    food_repo: FoodRepository = Depends(get_food_repo),
):
    goal = await user_repo.get_calorie_goal(user.id)
    target_cal = goal.target_calories if goal else 2000

    history_days = await food_repo.get_history_by_dates(user.id, limit_days=limit, offset_days=offset)
    results = []
    for d in history_days:
        pct = int(round((d["calories"] / target_cal) * 100)) if target_cal > 0 else 0
        results.append(
            HistoryDayResponse(
                date=d["date"],
                meals_count=d["meals_count"],
                calories=d["calories"],
                protein=d["protein"],
                fat=d["fat"],
                carbs=d["carbs"],
                target_calories=target_cal,
                percentage=pct,
            )
        )
    return results


@router.get("/{date}", response_model=List[FoodEntryResponse])
async def get_history_by_date(
    date: str,
    user: UserDB = Depends(get_current_user),
    food_repo: FoodRepository = Depends(get_food_repo),
):
    entries_db = await food_repo.get_entries_by_date(user.id, date)
    return [
        FoodEntryResponse(
            id=e.id,
            meal_type=e.meal_type,
            entry_date=e.entry_date,
            entry_time=e.entry_time,
            total_calories=e.total_calories,
            total_protein=e.total_protein,
            total_fat=e.total_fat,
            total_carbs=e.total_carbs,
            advice=e.advice,
            items=[
                FoodItemSchema(
                    id=it.id,
                    name=it.name,
                    portion_g=it.portion_g,
                    calories=it.calories,
                    protein_g=it.protein_g,
                    fat_g=it.fat_g,
                    carbs_g=it.carbs_g,
                )
                for it in e.items
            ]
        )
        for e in entries_db
    ]
