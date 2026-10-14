import os
import pytest
import pytest_asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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
    FoodAnalysisResult,
    FoodItemAnalysis,
    ReceiptAnalysisResult,
    ReceiptItemAnalysis,
    ExpenseParsedResult,
)
from app.config.settings import Settings


@pytest.fixture
def test_settings():
    return Settings(
        BOT_TOKEN="123456789:ABC_TEST_TOKEN",
        GEMINI_API_KEY="AIzaSyTestKey_ForTestingOnly",
        DATABASE_PATH=":memory:",
        DEFAULT_TIMEZONE="Asia/Almaty",
        LOG_LEVEL="DEBUG",
        MAX_IMAGE_SIZE_MB=5,
        RATE_LIMIT_PER_MINUTE=60,
    )


@pytest_asyncio.fixture
async def temp_db_manager():
    # Use a temporary file for SQLite to ensure connection sharing works across async tasks
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    db_manager = DatabaseManager(db_path)
    await db_manager.init_db()

    yield db_manager

    if db_path.exists():
        db_path.unlink()


@pytest_asyncio.fixture
async def user_repo(temp_db_manager):
    return UserRepository(temp_db_manager)


@pytest_asyncio.fixture
async def food_repo(temp_db_manager):
    return FoodRepository(temp_db_manager)


@pytest_asyncio.fixture
async def expense_repo(temp_db_manager):
    return ExpenseRepository(temp_db_manager)


@pytest_asyncio.fixture
async def reminder_repo(temp_db_manager):
    return ReminderRepository(temp_db_manager)


@pytest.fixture
def nutrition_service():
    return NutritionService()


@pytest.fixture
def mock_gemini_service():
    service = GeminiService(api_key="mock_key")

    # Mock analyze_food
    service.analyze_food = AsyncMock(return_value=FoodAnalysisResult(
        meal_name="Куриная грудка с рисом",
        items=[
            FoodItemAnalysis(name="Куриная грудка", portion_g=150, calories=248, protein_g=46.0, fat_g=5.0, carbs_g=0.0),
            FoodItemAnalysis(name="Рис варёный", portion_g=180, calories=230, protein_g=5.0, fat_g=1.0, carbs_g=50.0),
        ],
        total_calories=478,
        total_protein=51.0,
        total_fat=6.0,
        total_carbs=50.0,
        advice="Отличный баланс белков и сложных углеводов!",
    ))

    # Mock analyze_food_text
    service.analyze_food_text = AsyncMock(return_value=FoodAnalysisResult(
        meal_name="Овсяная каша",
        items=[
            FoodItemAnalysis(name="Овсянка", portion_g=200, calories=180, protein_g=6.0, fat_g=3.0, carbs_g=32.0),
        ],
        total_calories=180,
        total_protein=6.0,
        total_fat=3.0,
        total_carbs=32.0,
        advice="Хороший источник клетчатки на завтрак.",
    ))

    # Mock analyze_receipt
    service.analyze_receipt = AsyncMock(return_value=ReceiptAnalysisResult(
        merchant="Magnum Supermarket",
        date="2026-10-08",
        currency="₸",
        category="food",
        items=[
            ReceiptItemAnalysis(name="Молоко 3.2%", price=550.0, quantity=1.0),
            ReceiptItemAnalysis(name="Хлеб Бородинский", price=320.0, quantity=1.0),
        ],
        total_amount=870.0,
    ))

    # Mock parse_expense
    service.parse_expense = AsyncMock(return_value=ExpenseParsedResult(
        merchant="Кофейня",
        amount=1200.0,
        currency="₸",
        category="food",
        description="Капучино",
        items=[ReceiptItemAnalysis(name="Капучино", price=1200.0, quantity=1.0)],
    ))

    # Mock generate_food_advice
    service.generate_food_advice = AsyncMock(return_value="Сегодня у вас отличная норма белков. На ужин добавьте овощи.")

    return service


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.download = AsyncMock()
    return bot


@pytest.fixture
def app_instance(
    temp_db_manager,
    user_repo,
    food_repo,
    expense_repo,
    reminder_repo,
    nutrition_service,
    mock_gemini_service,
    mock_bot,
):
    from app.api.app import create_app
    from app.api.deps import setup_dependencies

    expense_service = ExpenseService(expense_repo)
    reminder_service = ReminderService(reminder_repo, bot=mock_bot)

    setup_dependencies(
        db_manager=temp_db_manager,
        user_repo=user_repo,
        food_repo=food_repo,
        expense_repo=expense_repo,
        reminder_repo=reminder_repo,
        nutrition_service=nutrition_service,
        gemini_service=mock_gemini_service,
        expense_service=expense_service,
        reminder_service=reminder_service,
    )
    return create_app()
