import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_db_manager, get_user_repo, get_nutrition_service
from app.database.models import UserDB, CalorieGoalDB
from app.database.connection import DatabaseManager
from app.database.repositories import UserRepository
from app.services import NutritionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


class WeightLogRequest(BaseModel):
    weight_kg: float = Field(..., ge=30.0, le=300.0)


class WaterLogRequest(BaseModel):
    amount_ml: int = Field(..., ge=10, le=5000)


@router.post("/weight")
async def log_weight(
    payload: WeightLogRequest,
    user: UserDB = Depends(get_current_user),
    db: DatabaseManager = Depends(get_db_manager),
    user_repo: UserRepository = Depends(get_user_repo),
    nutrition_service: NutritionService = Depends(get_nutrition_service),
):
    try:
        tz = ZoneInfo(user.timezone)
    except Exception:
        tz = ZoneInfo("Asia/Almaty")
    today_str = datetime.now(tz).strftime("%Y-%m-%d")

    new_weight = round(payload.weight_kg, 2)
    recalculated = False
    new_targets = None

    async with db.get_connection() as conn:
        # Save log
        await conn.execute(
            "INSERT INTO weight_logs (user_id, weight_kg, log_date, created_at) VALUES (?, ?, ?, ?);",
            (user.id, new_weight, today_str, datetime.utcnow().isoformat())
        )
        await conn.commit()

    # Check existing profile outside the insert connection context
    profile = await user_repo.get_profile(user.id)
    if profile:
        old_weight = profile.weight_kg
        # If weight shifted by >= 2.0 kg, auto-recalculate calorie and macro targets
        if abs(new_weight - old_weight) >= 2.0:
            profile.weight_kg = new_weight
            await user_repo.save_profile(profile)

            calc = nutrition_service.calculate_targets(
                gender=profile.gender,
                age=profile.age,
                height_cm=profile.height_cm,
                weight_kg=new_weight,
                activity_level=profile.activity_level,
                goal=profile.goal
            )
            goal_db = CalorieGoalDB(
                user_id=user.id,
                bmr=calc.bmr,
                tdee=calc.tdee,
                target_calories=calc.target_calories,
                target_protein_g=calc.target_protein_g,
                target_fat_g=calc.target_fat_g,
                target_carbs_g=calc.target_carbs_g,
            )
            await user_repo.save_calorie_goal(goal_db)
            recalculated = True
            new_targets = calc.model_dump()

    return {
        "success": True,
        "weight_kg": new_weight,
        "recalculated": recalculated,
        "targets": new_targets,
    }


@router.get("/weight")
async def get_weight_history(
    user: UserDB = Depends(get_current_user),
    db: DatabaseManager = Depends(get_db_manager),
):
    async with db.get_connection() as conn:
        cur = await conn.execute(
            "SELECT id, weight_kg, log_date, created_at FROM weight_logs WHERE user_id = ? ORDER BY id DESC LIMIT 30;",
            (user.id,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


@router.post("/water")
async def log_water(
    payload: WaterLogRequest,
    user: UserDB = Depends(get_current_user),
    db: DatabaseManager = Depends(get_db_manager),
):
    try:
        tz = ZoneInfo(user.timezone)
    except Exception:
        tz = ZoneInfo("Asia/Almaty")
    today_str = datetime.now(tz).strftime("%Y-%m-%d")

    async with db.get_connection() as conn:
        await conn.execute(
            "INSERT INTO water_logs (user_id, amount_ml, log_date, created_at) VALUES (?, ?, ?, ?);",
            (user.id, payload.amount_ml, today_str, datetime.utcnow().isoformat())
        )
        cur = await conn.execute(
            "SELECT SUM(amount_ml) as total FROM water_logs WHERE user_id = ? AND log_date = ?;",
            (user.id, today_str)
        )
        row = await cur.fetchone()
        tot = row["total"] or 0
        await conn.commit()

    return {"success": True, "amount_ml": payload.amount_ml, "today_total_ml": tot}


@router.get("/water/today")
async def get_today_water(
    user: UserDB = Depends(get_current_user),
    db: DatabaseManager = Depends(get_db_manager),
):
    try:
        tz = ZoneInfo(user.timezone)
    except Exception:
        tz = ZoneInfo("Asia/Almaty")
    today_str = datetime.now(tz).strftime("%Y-%m-%d")

    async with db.get_connection() as conn:
        cur = await conn.execute(
            "SELECT SUM(amount_ml) as total FROM water_logs WHERE user_id = ? AND log_date = ?;",
            (user.id, today_str)
        )
        row = await cur.fetchone()
        tot = row["total"] if row and row["total"] is not None else 0
        return {"today_total_ml": tot, "goal_ml": 2500}
