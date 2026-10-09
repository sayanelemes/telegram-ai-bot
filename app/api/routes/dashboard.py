from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends
from app.api.deps import (
    get_current_user,
    get_user_repo,
    get_food_repo,
    get_expense_repo,
)
from app.api.schemas import (
    DashboardResponse,
    CalorieSummary,
    MacrosSummary,
    MacroItem,
    FoodEntryResponse,
    FoodItemSchema,
)
from app.database.models import UserDB
from app.database.repositories import UserRepository, FoodRepository, ExpenseRepository

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    user: UserDB = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repo),
    food_repo: FoodRepository = Depends(get_food_repo),
    expense_repo: ExpenseRepository = Depends(get_expense_repo),
):
    try:
        tz = ZoneInfo(user.timezone)
    except Exception:
        tz = ZoneInfo("Asia/Almaty")

    today_str = datetime.now(tz).strftime("%Y-%m-%d")

    profile = await user_repo.get_profile(user.id)
    goal = await user_repo.get_calorie_goal(user.id)

    target_cal = goal.target_calories if goal else 2000
    target_prot = goal.target_protein_g if goal else 150
    target_fat = goal.target_fat_g if goal else 70
    target_carbs = goal.target_carbs_g if goal else 230

    daily_food = await food_repo.get_daily_totals(user.id, today_str)
    consumed_cal = daily_food["calories"]
    consumed_prot = daily_food["protein"]
    consumed_fat = daily_food["fat"]
    consumed_carbs = daily_food["carbs"]

    # Calculate remaining and exceeded according to Section 3 requirements
    remaining = max(0, target_cal - consumed_cal)
    exceeded = max(0, consumed_cal - target_cal)
    percentage = int(round((consumed_cal / target_cal) * 100)) if target_cal > 0 else 0

    # Fetch today's meals
    entries_db = await food_repo.get_entries_by_date(user.id, today_str)
    meals = [
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

    # Today's expenses
    today_expenses = await expense_repo.get_daily_total(user.id, today_str)

    return DashboardResponse(
        user_name=user.first_name or "Друг",
        timezone=user.timezone,
        is_profile_configured=profile is not None,
        calories=CalorieSummary(
            goal=target_cal,
            consumed=consumed_cal,
            remaining=remaining,
            exceeded=exceeded,
            percentage=percentage,
        ),
        macros=MacrosSummary(
            protein=MacroItem(goal=target_prot, consumed=consumed_prot),
            fat=MacroItem(goal=target_fat, consumed=consumed_fat),
            carbs=MacroItem(goal=target_carbs, consumed=consumed_carbs),
        ),
        meals=meals,
        today_expenses=today_expenses,
    )
