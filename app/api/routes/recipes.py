import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_recipe_service
from app.database.models import UserDB
from app.services.recipes import RecipeService
from app.services.gemini import GeminiServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["recipes"])


class RecipeSuggestRequest(BaseModel):
    mode: str = Field(default="remaining", description="'remaining' или 'custom'")
    custom_calories: Optional[int] = None
    custom_protein: Optional[float] = None
    custom_fat: Optional[float] = None
    custom_carbs: Optional[float] = None
    preferences: Optional[str] = None


class QuickLogRequest(BaseModel):
    request_id: str = Field(description="Уникальный ID запроса для защиты от повторных тапов (10 мин TTL)")
    recipe_data: Optional[Dict[str, Any]] = None
    meal_type: str = "meal"


class RecipeToExpenseRequest(BaseModel):
    recipe_data: Optional[Dict[str, Any]] = None
    custom_cost: Optional[float] = None


class WeeklyPlanRequest(BaseModel):
    preferences: Optional[str] = None


@router.post("/recipes/suggest")
async def suggest_recipe(
    payload: RecipeSuggestRequest,
    user: UserDB = Depends(get_current_user),
    recipe_service: RecipeService = Depends(get_recipe_service),
):
    try:
        recipe = await recipe_service.suggest_recipe(
            user_id=user.id,
            mode=payload.mode,
            custom_calories=payload.custom_calories,
            custom_protein=payload.custom_protein,
            custom_fat=payload.custom_fat,
            custom_carbs=payload.custom_carbs,
            preferences=payload.preferences,
            timezone_str=user.timezone,
        )
        return recipe
    except GeminiServiceError as ge:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(ge))
    except Exception as e:
        logger.error(f"Error in suggest_recipe: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка при подборе рецепта.")


@router.get("/recipes/last")
async def get_last_recipe(
    user: UserDB = Depends(get_current_user),
    recipe_service: RecipeService = Depends(get_recipe_service),
):
    recipe = await recipe_service.get_last_recipe(user.id)
    if not recipe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Нет сохранённого рецепта или истёк срок 24 часа.")
    return recipe


@router.post("/meals/quick-log")
async def quick_log_meal(
    payload: QuickLogRequest,
    user: UserDB = Depends(get_current_user),
    recipe_service: RecipeService = Depends(get_recipe_service),
):
    try:
        result = await recipe_service.quick_log_meal(
            user_id=user.id,
            request_id=payload.request_id,
            recipe_data=payload.recipe_data,
            meal_type=payload.meal_type,
            timezone_str=user.timezone,
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Error in quick_log_meal: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка при быстрой записи блюда.")


@router.post("/recipes/to-expense")
async def save_recipe_to_expense(
    payload: RecipeToExpenseRequest,
    user: UserDB = Depends(get_current_user),
    recipe_service: RecipeService = Depends(get_recipe_service),
):
    try:
        result = await recipe_service.save_recipe_to_expenses(
            user_id=user.id,
            recipe_data=payload.recipe_data,
            custom_cost=payload.custom_cost,
            timezone_str=user.timezone,
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Error in save_recipe_to_expense: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка при записи продуктов в расходы.")


@router.post("/recipes/weekly-plan")
async def generate_weekly_meal_plan(
    payload: WeeklyPlanRequest,
    user: UserDB = Depends(get_current_user),
    recipe_service: RecipeService = Depends(get_recipe_service),
):
    try:
        plan = await recipe_service.generate_weekly_meal_plan(
            user_id=user.id,
            preferences=payload.preferences,
        )
        return plan
    except GeminiServiceError as ge:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(ge))
    except Exception as e:
        logger.error(f"Error in generate_weekly_meal_plan: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка генерации недельного плана.")


@router.get("/recipes/weekly-plan")
async def get_weekly_meal_plan(
    user: UserDB = Depends(get_current_user),
    recipe_service: RecipeService = Depends(get_recipe_service),
):
    plan = await recipe_service.get_weekly_meal_plan(user.id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="План питания ещё не создан.")
    return plan
