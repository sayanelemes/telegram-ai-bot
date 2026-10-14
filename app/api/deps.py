from typing import AsyncGenerator, Optional
from fastapi import Depends, Header
from app.config.settings import settings
from app.database.connection import DatabaseManager
from app.database.models import UserDB
from app.database.repositories import (
    UserRepository,
    FoodRepository,
    ExpenseRepository,
    ReminderRepository,
)
from app.services import (
    NutritionService,
    GeminiService,
    ExpenseService,
    ReminderService,
)
from app.api.auth import get_current_user_from_init_data

# Singleton references set during app startup
_db_manager: Optional[DatabaseManager] = None
_user_repo: Optional[UserRepository] = None
_food_repo: Optional[FoodRepository] = None
_expense_repo: Optional[ExpenseRepository] = None
_reminder_repo: Optional[ReminderRepository] = None
_nutrition_service: Optional[NutritionService] = None
_gemini_service: Optional[GeminiService] = None
_expense_service: Optional[ExpenseService] = None
_reminder_service: Optional[ReminderService] = None


def setup_dependencies(
    db_manager: DatabaseManager,
    user_repo: UserRepository,
    food_repo: FoodRepository,
    expense_repo: ExpenseRepository,
    reminder_repo: ReminderRepository,
    nutrition_service: NutritionService,
    gemini_service: GeminiService,
    expense_service: ExpenseService,
    reminder_service: ReminderService,
) -> None:
    global _db_manager, _user_repo, _food_repo, _expense_repo, _reminder_repo
    global _nutrition_service, _gemini_service, _expense_service, _reminder_service

    _db_manager = db_manager
    _user_repo = user_repo
    _food_repo = food_repo
    _expense_repo = expense_repo
    _reminder_repo = reminder_repo
    _nutrition_service = nutrition_service
    _gemini_service = gemini_service
    _expense_service = expense_service
    _reminder_service = reminder_service


def get_db_manager() -> DatabaseManager:
    assert _db_manager is not None, "DatabaseManager not initialized"
    return _db_manager


def get_user_repo() -> UserRepository:
    assert _user_repo is not None, "UserRepository not initialized"
    return _user_repo


def get_food_repo() -> FoodRepository:
    assert _food_repo is not None, "FoodRepository not initialized"
    return _food_repo


def get_expense_repo() -> ExpenseRepository:
    assert _expense_repo is not None, "ExpenseRepository not initialized"
    return _expense_repo


def get_reminder_repo() -> ReminderRepository:
    assert _reminder_repo is not None, "ReminderRepository not initialized"
    return _reminder_repo


def get_nutrition_service() -> NutritionService:
    assert _nutrition_service is not None, "NutritionService not initialized"
    return _nutrition_service


def get_gemini_service() -> GeminiService:
    assert _gemini_service is not None, "GeminiService not initialized"
    return _gemini_service


def get_expense_service() -> ExpenseService:
    assert _expense_service is not None, "ExpenseService not initialized"
    return _expense_service


def get_reminder_service() -> ReminderService:
    assert _reminder_service is not None, "ReminderService not initialized"
    return _reminder_service


def get_stats_service(
    user_repo: UserRepository = Depends(get_user_repo),
    food_repo: FoodRepository = Depends(get_food_repo),
    expense_repo: ExpenseRepository = Depends(get_expense_repo),
) -> "StatsService":
    from app.services.stats import StatsService
    return StatsService(user_repo=user_repo, food_repo=food_repo, expense_repo=expense_repo)


def get_recipe_service(
    db_manager: DatabaseManager = Depends(get_db_manager),
    user_repo: UserRepository = Depends(get_user_repo),
    food_repo: FoodRepository = Depends(get_food_repo),
    expense_repo: ExpenseRepository = Depends(get_expense_repo),
    gemini_service: GeminiService = Depends(get_gemini_service),
) -> "RecipeService":
    from app.services.recipes import RecipeService
    return RecipeService(
        db_manager=db_manager,
        user_repo=user_repo,
        food_repo=food_repo,
        expense_repo=expense_repo,
        gemini_service=gemini_service,
    )



async def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data"),
    x_auth_token: Optional[str] = Header(None, alias="X-Auth-Token"),
    x_dev_user_id: Optional[str] = Header(None, alias="X-Dev-User-Id"),
    user_repo: UserRepository = Depends(get_user_repo),
) -> UserDB:
    return await get_current_user_from_init_data(
        authorization=authorization,
        x_telegram_init_data=x_telegram_init_data,
        x_auth_token=x_auth_token,
        x_dev_user_id=x_dev_user_id,
        user_repo=user_repo,
    )
