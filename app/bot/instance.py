import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config.settings import Settings
from app.bot.middlewares import ThrottlingMiddleware, ErrorHandlingMiddleware
from app.handlers import all_routers
from app.database.connection import DatabaseManager
from app.database.repositories import (
    UserRepository,
    FoodRepository,
    ExpenseRepository,
    ReminderRepository,
)
from app.database.repositories.productivity_repository import ProductivityRepository
from app.services import (
    NutritionService,
    GeminiService,
    ExpenseService,
    ReminderService,
    UnifiedSchedulerService,
)

logger = logging.getLogger(__name__)


def create_bot(settings: Settings) -> Bot:
    return Bot(token=settings.BOT_TOKEN)


def create_dispatcher(
    settings: Settings,
    db_manager: DatabaseManager,
    user_repo: UserRepository,
    food_repo: FoodRepository,
    expense_repo: ExpenseRepository,
    reminder_repo: ReminderRepository,
    nutrition_service: NutritionService,
    gemini_service: GeminiService,
    expense_service: ExpenseService,
    reminder_service: ReminderService,
    productivity_repo: ProductivityRepository | None = None,
    unified_scheduler_service: UnifiedSchedulerService | None = None,
) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    # Register Middlewares
    dp.message.middleware(ThrottlingMiddleware(rate_limit_per_minute=settings.RATE_LIMIT_PER_MINUTE))
    dp.callback_query.middleware(ThrottlingMiddleware(rate_limit_per_minute=settings.RATE_LIMIT_PER_MINUTE))
    dp.message.middleware(ErrorHandlingMiddleware())
    dp.callback_query.middleware(ErrorHandlingMiddleware())

    if productivity_repo is None:
        productivity_repo = ProductivityRepository(db_manager)

    # Dependency Injection into aiogram handler kwargs
    dp["settings"] = settings
    dp["db_manager"] = db_manager
    dp["user_repo"] = user_repo
    dp["food_repo"] = food_repo
    dp["expense_repo"] = expense_repo
    dp["reminder_repo"] = reminder_repo
    dp["productivity_repo"] = productivity_repo
    dp["nutrition_service"] = nutrition_service
    dp["gemini_service"] = gemini_service
    dp["expense_service"] = expense_service
    dp["reminder_service"] = reminder_service
    dp["unified_scheduler_service"] = unified_scheduler_service

    # Include all routers
    for router in all_routers:
        dp.include_router(router)

    return dp
