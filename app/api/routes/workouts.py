import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_workout_service, get_workout_repo
from app.database.models import UserDB
from app.services.workout import WorkoutService
from app.database.repositories.workout_repository import WorkoutRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workouts", tags=["Workouts"])


class PlanGenerateRequest(BaseModel):
    goal: str = "набор массы (гипертрофия)"
    experience: str = "средний"
    equipment: str = "зал"  # зал / гантели дома / турник
    days_per_week: int = Field(4, ge=2, le=6)


class PlanModifyRequest(BaseModel):
    instruction: str


class WorkoutLogRequest(BaseModel):
    text: str  # e.g. "жим 60x8x3, разводка 12х10х3"
    workout_date: Optional[str] = None


@router.get("/plan", response_model=Optional[Dict[str, Any]])
async def get_active_plan(
    current_user: UserDB = Depends(get_current_user),
    workout_repo: WorkoutRepository = Depends(get_workout_repo),
):
    """Get active workout plan for current user."""
    return await workout_repo.get_active_plan(user_id=current_user.id)


@router.post("/plan/generate", response_model=Dict[str, Any])
async def generate_workout_plan(
    payload: PlanGenerateRequest,
    current_user: UserDB = Depends(get_current_user),
    workout_service: WorkoutService = Depends(get_workout_service),
):
    """Generate a bulking workout plan tailored to goals, experience, and equipment via Gemini."""
    return await workout_service.generate_plan(
        user_id=current_user.id,
        goal=payload.goal,
        experience=payload.experience,
        equipment=payload.equipment,
        days_per_week=payload.days_per_week,
    )


@router.post("/plan/modify", response_model=Dict[str, Any])
async def modify_workout_plan(
    payload: PlanModifyRequest,
    current_user: UserDB = Depends(get_current_user),
    workout_service: WorkoutService = Depends(get_workout_service),
):
    """Modify current active workout plan using plain language instructions via Gemini."""
    if not payload.instruction.strip():
        raise HTTPException(status_code=400, detail="Instruction cannot be empty")
    return await workout_service.modify_plan(
        user_id=current_user.id,
        instruction=payload.instruction,
    )


@router.post("/log", response_model=Dict[str, Any])
async def log_workout_exercises(
    payload: WorkoutLogRequest,
    current_user: UserDB = Depends(get_current_user),
    workout_service: WorkoutService = Depends(get_workout_service),
):
    """
    Log exercises from text (e.g. 'жим 60x8x3, разводка 12х10х3').
    Detects PRs, computes total tonnage, and provides bulking anabolic window nutrition reminder.
    """
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Workout text cannot be empty")

    result = await workout_service.log_workout(
        user_id=current_user.id,
        text=payload.text,
        workout_date=payload.workout_date,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to parse workout"))
    return result


@router.get("/history", response_model=List[Dict[str, Any]])
async def get_workout_history(
    limit: int = Query(50, ge=1, le=200),
    current_user: UserDB = Depends(get_current_user),
    workout_repo: WorkoutRepository = Depends(get_workout_repo),
):
    """Get past workout logs."""
    return await workout_repo.get_workout_history(user_id=current_user.id, limit=limit)


@router.get("/prs", response_model=List[Dict[str, Any]])
async def get_personal_records(
    current_user: UserDB = Depends(get_current_user),
    workout_repo: WorkoutRepository = Depends(get_workout_repo),
):
    """Get all personal records (PRs) per exercise."""
    return await workout_repo.get_user_prs(user_id=current_user.id)


@router.get("/exercise/{exercise_name}/chart", response_model=Dict[str, Any])
async def get_exercise_chart(
    exercise_name: str,
    limit: int = Query(30, ge=2, le=100),
    current_user: UserDB = Depends(get_current_user),
    workout_repo: WorkoutRepository = Depends(get_workout_repo),
    workout_service: WorkoutService = Depends(get_workout_service),
):
    """Get weight progression history and self-contained SVG chart for an exercise."""
    history = await workout_repo.get_exercise_history(
        user_id=current_user.id,
        exercise_name=exercise_name,
        limit=limit,
    )
    svg_chart = workout_service.generate_svg_chart(exercise_name, history)
    return {
        "exercise_name": exercise_name,
        "points_count": len(history),
        "history": history,
        "svg_markup": svg_chart,
    }


@router.get("/progression", response_model=Dict[str, Any])
async def get_progression_recommendation(
    exercise_name: str = Query(...),
    current_weight: float = Query(...),
    success: bool = Query(True),
    failures: int = Query(0),
    current_user: UserDB = Depends(get_current_user),
    workout_service: WorkoutService = Depends(get_workout_service),
):
    """
    Get progressive overload step (+2.5 kg on success, maintain on 2 failures).
    """
    return workout_service.get_progression_recommendation(
        exercise_name=exercise_name,
        current_weight=current_weight,
        success=success,
        recent_failures_count=failures,
    )
