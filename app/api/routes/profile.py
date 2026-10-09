from fastapi import APIRouter, Depends, HTTPException, status
from app.api.deps import (
    get_current_user,
    get_user_repo,
    get_nutrition_service,
)
from app.api.schemas import ProfileResponse, ProfileUpdateRequest
from app.database.models import UserDB, UserProfileDB, CalorieGoalDB
from app.database.repositories import UserRepository
from app.services import NutritionService

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileResponse)
async def get_profile(
    user: UserDB = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repo),
):
    profile = await user_repo.get_profile(user.id)
    goal = await user_repo.get_calorie_goal(user.id)

    return ProfileResponse(
        gender=profile.gender if profile else None,
        age=profile.age if profile else None,
        height_cm=profile.height_cm if profile else None,
        weight_kg=profile.weight_kg if profile else None,
        activity_level=profile.activity_level if profile else None,
        goal=profile.goal if profile else None,
        bmr=goal.bmr if goal else None,
        tdee=goal.tdee if goal else None,
        target_calories=goal.target_calories if goal else None,
        target_protein_g=goal.target_protein_g if goal else None,
        target_fat_g=goal.target_fat_g if goal else None,
        target_carbs_g=goal.target_carbs_g if goal else None,
        timezone=user.timezone,
    )


@router.patch("", response_model=ProfileResponse)
async def update_profile(
    payload: ProfileUpdateRequest,
    user: UserDB = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repo),
    nutrition_service: NutritionService = Depends(get_nutrition_service),
):
    # Validate with service
    val = nutrition_service.validate_inputs(
        gender=payload.gender,
        age=payload.age,
        height_cm=payload.height_cm,
        weight_kg=payload.weight_kg,
        activity_level=payload.activity_level,
        goal=payload.goal,
    )
    if not val.is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=val.error_message)

    # Save profile
    profile = UserProfileDB(
        user_id=user.id,
        gender=payload.gender,
        age=payload.age,
        height_cm=payload.height_cm,
        weight_kg=payload.weight_kg,
        activity_level=payload.activity_level,
        goal=payload.goal,
    )
    await user_repo.save_profile(profile)

    # Recalculate targets using Mifflin-St Jeor
    targets = nutrition_service.calculate_targets(
        gender=payload.gender,
        age=payload.age,
        height_cm=payload.height_cm,
        weight_kg=payload.weight_kg,
        activity_level=payload.activity_level,
        goal=payload.goal,
    )
    goal_db = CalorieGoalDB(
        user_id=user.id,
        bmr=targets.bmr,
        tdee=targets.tdee,
        target_calories=targets.target_calories,
        target_protein_g=targets.target_protein_g,
        target_fat_g=targets.target_fat_g,
        target_carbs_g=targets.target_carbs_g,
    )
    await user_repo.save_calorie_goal(goal_db)

    return ProfileResponse(
        gender=profile.gender,
        age=profile.age,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        activity_level=profile.activity_level,
        goal=profile.goal,
        bmr=targets.bmr,
        tdee=targets.tdee,
        target_calories=targets.target_calories,
        target_protein_g=targets.target_protein_g,
        target_fat_g=targets.target_fat_g,
        target_carbs_g=targets.target_carbs_g,
        timezone=user.timezone,
    )
