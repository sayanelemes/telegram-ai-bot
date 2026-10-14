from __future__ import annotations
from typing import Optional
from fastapi import Depends, Header
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
    StatsService,
    RecipeService,
)
from app.api.auth import get_current_user_from_init_data

from app.database.repositories.productivity_repository import ProductivityRepository
from app.database.repositories.workout_repository import WorkoutRepository
from app.database.repositories.finance_repository import FinanceRepository
from app.database.repositories.insights_repository import InsightsRepository
from app.services.unified_scheduler import UnifiedSchedulerService
from app.services.workout import WorkoutService
from app.services.insights import InsightsService

# Singleton references set during app startup
_db_manager: Optional[DatabaseManager] = None
_user_repo: Optional[UserRepository] = None
_food_repo: Optional[FoodRepository] = None
_expense_repo: Optional[ExpenseRepository] = None
_reminder_repo: Optional[ReminderRepository] = None
_productivity_repo: Optional[ProductivityRepository] = None
_workout_repo: Optional[WorkoutRepository] = None
_finance_repo: Optional[FinanceRepository] = None
_insights_repo: Optional[InsightsRepository] = None
_insights_service: Optional[InsightsService] = None
_nutrition_service: Optional[NutritionService] = None
_gemini_service: Optional[GeminiService] = None
_expense_service: Optional[ExpenseService] = None
_reminder_service: Optional[ReminderService] = None
_unified_scheduler_service: Optional[UnifiedSchedulerService] = None


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
    productivity_repo: Optional[ProductivityRepository] = None,
    unified_scheduler_service: Optional[UnifiedSchedulerService] = None,
    workout_repo: Optional[WorkoutRepository] = None,
    finance_repo: Optional[FinanceRepository] = None,
    insights_repo: Optional[InsightsRepository] = None,
    insights_service: Optional[InsightsService] = None,
) -> None:
    global _db_manager, _user_repo, _food_repo, _expense_repo, _reminder_repo, _productivity_repo, _workout_repo, _finance_repo, _insights_repo
    global _nutrition_service, _gemini_service, _expense_service, _reminder_service, _unified_scheduler_service, _insights_service

    _db_manager = db_manager
    _user_repo = user_repo
    _food_repo = food_repo
    _expense_repo = expense_repo
    _reminder_repo = reminder_repo
    _productivity_repo = productivity_repo or ProductivityRepository(db_manager)
    _workout_repo = workout_repo or WorkoutRepository(db_manager)
    _finance_repo = finance_repo or FinanceRepository(db_manager)
    _insights_repo = insights_repo or InsightsRepository(db_manager)
    _nutrition_service = nutrition_service
    _gemini_service = gemini_service
    _expense_service = expense_service
    _reminder_service = reminder_service
    _unified_scheduler_service = unified_scheduler_service
    _insights_service = insights_service or InsightsService(
        db_manager=db_manager,
        insights_repo=_insights_repo,
        user_repo=user_repo,
        food_repo=food_repo,
        expense_repo=expense_repo,
        productivity_repo=_productivity_repo,
        workout_repo=_workout_repo,
        gemini_service=gemini_service,
    )


def get_db_manager() -> DatabaseManager:
    assert _db_manager is not None, "DatabaseManager not initialized"
    return _db_manager


def get_productivity_repo() -> ProductivityRepository:
    global _productivity_repo
    if _productivity_repo is None and _db_manager is not None:
        _productivity_repo = ProductivityRepository(_db_manager)
    assert _productivity_repo is not None, "ProductivityRepository not initialized"
    return _productivity_repo


def get_workout_repo() -> WorkoutRepository:
    global _workout_repo
    if _workout_repo is None and _db_manager is not None:
        _workout_repo = WorkoutRepository(_db_manager)
    assert _workout_repo is not None, "WorkoutRepository not initialized"
    return _workout_repo


def get_finance_repo() -> FinanceRepository:
    global _finance_repo
    if _finance_repo is None and _db_manager is not None:
        _finance_repo = FinanceRepository(_db_manager)
    assert _finance_repo is not None, "FinanceRepository not initialized"
    return _finance_repo


def get_insights_repo() -> InsightsRepository:
    global _insights_repo
    if _insights_repo is None and _db_manager is not None:
        _insights_repo = InsightsRepository(_db_manager)
    assert _insights_repo is not None, "InsightsRepository not initialized"
    return _insights_repo


def get_insights_service() -> InsightsService:
    global _insights_service
    assert _insights_service is not None, "InsightsService not initialized"
    return _insights_service


def get_workout_service(
    workout_repo: WorkoutRepository = Depends(get_workout_repo),
    user_repo: UserRepository = Depends(lambda: _user_repo),
    gemini_service: GeminiService = Depends(lambda: _gemini_service),
) -> WorkoutService:
    assert _user_repo is not None
    assert _gemini_service is not None
    return WorkoutService(
        workout_repo=workout_repo,
        user_repo=_user_repo,
        gemini_service=_gemini_service,
    )


def get_unified_scheduler_service() -> Optional[UnifiedSchedulerService]:
    return _unified_scheduler_service


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
) -> StatsService:
    return StatsService(user_repo=user_repo, food_repo=food_repo, expense_repo=expense_repo)


def get_recipe_service(
    db_manager: DatabaseManager = Depends(get_db_manager),
    user_repo: UserRepository = Depends(get_user_repo),
    food_repo: FoodRepository = Depends(get_food_repo),
    expense_repo: ExpenseRepository = Depends(get_expense_repo),
    gemini_service: GeminiService = Depends(get_gemini_service),
) -> RecipeService:
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
