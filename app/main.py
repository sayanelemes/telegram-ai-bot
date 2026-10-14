import asyncio
import logging
import sys
from pathlib import Path
import uvicorn

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import settings
from app.utils.logging import setup_logging
from app.database.connection import DatabaseManager
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
from app.bot.instance import create_bot, create_dispatcher
from app.api import create_app, setup_dependencies

logger = logging.getLogger(__name__)


async def main() -> None:
    # 1. Setup logging
    setup_logging(log_level=settings.LOG_LEVEL)
    logger.info("Starting Telegram Nutrition & Expense AI Assistant (Bot + FastAPI Mini App)...")

    if not settings.BOT_TOKEN:
        logger.error("BOT_TOKEN is not configured in .env file! Please set BOT_TOKEN to run the bot.")
        sys.exit(1)

    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY is not set. Gemini AI features will raise errors until key is set.")

    # 2. Database initialization
    db_manager = DatabaseManager(settings.resolved_db_path)
    await db_manager.init_db()

    # 3. Repositories
    user_repo = UserRepository(db_manager)
    food_repo = FoodRepository(db_manager)
    expense_repo = ExpenseRepository(db_manager)
    reminder_repo = ReminderRepository(db_manager)
    from app.database.repositories.productivity_repository import ProductivityRepository
    productivity_repo = ProductivityRepository(db_manager)
    from app.database.repositories.workout_repository import WorkoutRepository
    workout_repo = WorkoutRepository(db_manager)
    from app.database.repositories.finance_repository import FinanceRepository
    finance_repo = FinanceRepository(db_manager)
    from app.database.repositories.insights_repository import InsightsRepository
    insights_repo = InsightsRepository(db_manager)

    # 4. Services
    nutrition_service = NutritionService()
    gemini_service = GeminiService(
        api_key=settings.GEMINI_API_KEY,
        model_name=settings.GEMINI_MODEL
    )
    expense_service = ExpenseService(expense_repo)
    reminder_service = ReminderService(reminder_repo)
    from app.services.unified_scheduler import UnifiedSchedulerService
    unified_scheduler_service = UnifiedSchedulerService(
        productivity_repo=productivity_repo,
        user_repo=user_repo,
        food_repo=food_repo,
    )

    # 5. Wire up FastAPI dependencies
    setup_dependencies(
        db_manager=db_manager,
        user_repo=user_repo,
        food_repo=food_repo,
        expense_repo=expense_repo,
        reminder_repo=reminder_repo,
        nutrition_service=nutrition_service,
        gemini_service=gemini_service,
        expense_service=expense_service,
        reminder_service=reminder_service,
        productivity_repo=productivity_repo,
        unified_scheduler_service=unified_scheduler_service,
        workout_repo=workout_repo,
        finance_repo=finance_repo,
        insights_repo=insights_repo,
    )
    fastapi_app = create_app()

    # 6. Start Uvicorn web server in background
    uvicorn_config = uvicorn.Config(
        app=fastapi_app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=False,
    )
    server = uvicorn.Server(uvicorn_config)
    server_task = asyncio.create_task(server.serve())
    logger.info(f"FastAPI Web Server listening on http://{settings.API_HOST}:{settings.API_PORT}")

    # 7. Bot & Dispatcher
    bot = create_bot(settings)
    reminder_service.set_bot(bot)
    unified_scheduler_service.set_bot(bot)

    # 8. Start schedulers & sync jobs
    reminder_service.start()
    await reminder_service.sync_all_jobs()
    unified_scheduler_service.start()

    dp = create_dispatcher(
        settings=settings,
        db_manager=db_manager,
        user_repo=user_repo,
        food_repo=food_repo,
        expense_repo=expense_repo,
        reminder_repo=reminder_repo,
        nutrition_service=nutrition_service,
        gemini_service=gemini_service,
        expense_service=expense_service,
        reminder_service=reminder_service,
        productivity_repo=productivity_repo,
        unified_scheduler_service=unified_scheduler_service,
    )

    try:
        # Delete pending webhook updates if any, then start polling
        await bot.delete_webhook(drop_pending_updates=True)
        if settings.WEB_APP_URL:
            from aiogram.types import MenuButtonWebApp, WebAppInfo
            try:
                await bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(text="🚀 Приложение", web_app=WebAppInfo(url=settings.WEB_APP_URL))
                )
            except Exception as e:
                logger.warning(f"Failed to set default WebApp menu button: {e}")
        logger.info("Bot polling started successfully.")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Application is shutting down...")
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(server_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        reminder_service.shutdown()
        await bot.session.close()
        logger.info("Application shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
