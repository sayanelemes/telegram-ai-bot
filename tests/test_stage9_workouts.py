import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from app.database.connection import DatabaseManager
from app.database.models import CalorieGoalDB
from app.database.repositories.user_repository import UserRepository
from app.database.repositories.food_repository import FoodRepository
from app.database.repositories.expense_repository import ExpenseRepository
from app.database.repositories.reminder_repository import ReminderRepository
from app.database.repositories.productivity_repository import ProductivityRepository
from app.database.repositories.workout_repository import WorkoutRepository
from app.services.gemini import GeminiService
from app.services.nutrition import NutritionService
from app.services.expenses import ExpenseService
from app.services.reminders import ReminderService
from app.services.workout import (
    WorkoutService,
    WorkoutPlanSchema,
    PlanDaySchema,
    PlanExerciseSchema,
)
from app.api.deps import setup_dependencies
from app.api.app import create_app


@pytest.fixture
async def workout_db(tmp_path):
    db_file = tmp_path / "test_stage9.db"
    db_manager = DatabaseManager(db_file)
    await db_manager.init_db()
    return db_manager


@pytest.fixture
async def user_repo_s9(workout_db):
    return UserRepository(workout_db)


@pytest.fixture
async def workout_repo_s9(workout_db):
    return WorkoutRepository(workout_db)


@pytest.fixture
def mock_gemini_s9():
    service = MagicMock(spec=GeminiService)
    service.call_structured = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_workout_repo_pr_and_tonnage(workout_repo_s9, user_repo_s9):
    user = await user_repo_s9.get_or_create_user(telegram_id=9001, timezone="Asia/Almaty")

    # Log 1: Жим лежа 60 кг x 8 x 3 -> First time, is_pr = True
    l1 = await workout_repo_s9.log_exercise(
        user_id=user.id,
        workout_date="2026-10-14",
        exercise_name="Жим лежа",
        weight_kg=60.0,
        reps=8,
        sets=3,
    )
    assert l1["is_pr"] is True
    assert l1["volume_kg"] == 60.0 * 8 * 3  # 1440 kg

    # Log 2: Жим лежа 55 кг x 10 x 3 -> Lower weight than 60, is_pr = False
    l2 = await workout_repo_s9.log_exercise(
        user_id=user.id,
        workout_date="2026-10-14",
        exercise_name="Жим лежа",
        weight_kg=55.0,
        reps=10,
        sets=3,
    )
    assert l2["is_pr"] is False

    # Log 3: Жим лежа 62.5 кг x 6 x 3 -> New PR!
    l3 = await workout_repo_s9.log_exercise(
        user_id=user.id,
        workout_date="2026-10-14",
        exercise_name="Жим лежа",
        weight_kg=62.5,
        reps=6,
        sets=3,
    )
    assert l3["is_pr"] is True

    # Total volume
    vol = await workout_repo_s9.get_total_volume_for_day(user.id, "2026-10-14")
    expected_vol = (60.0 * 8 * 3) + (55.0 * 10 * 3) + (62.5 * 6 * 3)
    assert vol == round(expected_vol, 1)

    # Check has_workout_today
    assert await workout_repo_s9.has_workout_today(user.id, "2026-10-14") is True
    assert await workout_repo_s9.has_workout_today(user.id, "2026-10-15") is False

    # PR list
    prs = await workout_repo_s9.get_user_prs(user.id)
    assert len(prs) == 1
    assert prs[0]["exercise_name"] == "Жим лежа"
    assert prs[0]["max_weight"] == 62.5


@pytest.mark.asyncio
async def test_regex_parser_multiple_exercises(workout_repo_s9, user_repo_s9, mock_gemini_s9):
    service = WorkoutService(workout_repo_s9, user_repo_s9, mock_gemini_s9)

    text = "жим 60x8x3, разводка 12х10х3, присед 100 5х5, тяга 80x6x4 @8.5"
    items = service.parse_workout_text_regex(text)

    assert len(items) == 4
    assert items[0]["exercise_name"] == "Жим"
    assert items[0]["weight_kg"] == 60.0
    assert items[0]["reps"] == 8
    assert items[0]["sets"] == 3

    assert items[1]["exercise_name"] == "Разводка"
    assert items[1]["weight_kg"] == 12.0
    assert items[1]["reps"] == 10
    assert items[1]["sets"] == 3

    assert items[2]["exercise_name"] == "Присед"
    assert items[2]["weight_kg"] == 100.0
    assert items[2]["reps"] == 5
    assert items[2]["sets"] == 5

    assert items[3]["exercise_name"] == "Тяга"
    assert items[3]["weight_kg"] == 80.0
    assert items[3]["rpe"] == 8.5


@pytest.mark.asyncio
async def test_workout_log_anabolic_window_and_calorie_boost(workout_repo_s9, user_repo_s9, mock_gemini_s9):
    user = await user_repo_s9.get_or_create_user(telegram_id=9002, timezone="Asia/Almaty")
    await user_repo_s9.save_calorie_goal(
        CalorieGoalDB(
            user_id=user.id,
            bmr=1800,
            tdee=2400,
            target_calories=2500,
            target_protein_g=150,
            target_fat_g=80,
            target_carbs_g=300,
        )
    )

    service = WorkoutService(workout_repo_s9, user_repo_s9, mock_gemini_s9)
    res = await service.log_workout(
        user_id=user.id,
        text="жим 70x8x3, брусья 15x8x3",
        workout_date="2026-10-14",
    )

    assert res["success"] is True
    assert res["tonnage_kg"] == (70 * 8 * 3) + (15 * 8 * 3)
    assert res["prs_count"] == 2
    assert res["boosted_calories"] == 2750  # 2500 * 1.10 = 2750
    assert "Анаболическое окно" in res["reminder_message"]
    assert "+10%" in res["reminder_message"]
    assert "30-40 г белка" in res["reminder_message"]


@pytest.mark.asyncio
async def test_progressive_overload_recommendation(workout_repo_s9, user_repo_s9, mock_gemini_s9):
    service = WorkoutService(workout_repo_s9, user_repo_s9, mock_gemini_s9)

    # Success completed -> +2.5 kg
    rec_success = service.get_progression_recommendation(
        exercise_name="Жим лежа",
        current_weight=70.0,
        success=True,
    )
    assert rec_success["next_recommended_weight"] == 72.5
    assert rec_success["status"] == "increment"
    assert "+2.5 кг" in rec_success["recommendation"]

    # 1st failure -> retry same weight
    rec_retry = service.get_progression_recommendation(
        exercise_name="Жим лежа",
        current_weight=72.5,
        success=False,
        recent_failures_count=1,
    )
    assert rec_retry["next_recommended_weight"] == 72.5
    assert rec_retry["status"] == "retry"

    # 2nd failure -> plateau hold
    rec_hold = service.get_progression_recommendation(
        exercise_name="Жим лежа",
        current_weight=72.5,
        success=False,
        recent_failures_count=2,
    )
    assert rec_hold["next_recommended_weight"] == 72.5
    assert rec_hold["status"] == "plateau_hold"
    assert "2 тренировки подряд" in rec_hold["recommendation"]


@pytest.mark.asyncio
async def test_svg_chart_generation(workout_repo_s9, user_repo_s9, mock_gemini_s9):
    service = WorkoutService(workout_repo_s9, user_repo_s9, mock_gemini_s9)

    logs = [
        {"workout_date": "2026-10-01", "weight_kg": 60.0, "is_pr": True},
        {"workout_date": "2026-10-05", "weight_kg": 62.5, "is_pr": True},
        {"workout_date": "2026-10-10", "weight_kg": 62.5, "is_pr": False},
        {"workout_date": "2026-10-14", "weight_kg": 65.0, "is_pr": True},
    ]

    svg = service.generate_svg_chart("Жим лежа", logs)
    assert "<svg" in svg
    assert "</svg>" in svg
    assert "<polyline" in svg
    assert "65.0" in svg
    assert "2026-10-01" in svg
    assert "2026-10-14" in svg


@pytest.mark.asyncio
async def test_plan_generation_and_modification_mocked(workout_repo_s9, user_repo_s9, mock_gemini_s9):
    user = await user_repo_s9.get_or_create_user(telegram_id=9003, timezone="Asia/Almaty")

    # Mock plan generation
    mock_plan = WorkoutPlanSchema(
        name="Массонабор 4 дня",
        days_per_week=4,
        description="Фокус на базовые движения",
        days=[
            PlanDaySchema(
                day_name="День 1: Грудь",
                exercises=[PlanExerciseSchema(name="Жим штанги лежа", sets=4, reps="8-10", rest_sec=120)]
            )
        ]
    )
    mock_gemini_s9.call_structured.return_value = mock_plan

    service = WorkoutService(workout_repo_s9, user_repo_s9, mock_gemini_s9)

    plan = await service.generate_plan(user_id=user.id, equipment="зал", days_per_week=4)
    assert plan["name"] == "Массонабор 4 дня"
    assert len(plan["plan_data"]["days"]) == 1

    # Mock plan modification
    modified_plan = WorkoutPlanSchema(
        name="Массонабор 4 дня (Модифицированный)",
        days_per_week=4,
        description="Заменена становая на румынскую тягу",
        days=[
            PlanDaySchema(
                day_name="День 1: Грудь и Румынка",
                exercises=[PlanExerciseSchema(name="Румынская тяга", sets=3, reps="10-12", rest_sec=120)]
            )
        ]
    )
    mock_gemini_s9.call_structured.return_value = modified_plan

    mod_res = await service.modify_plan(user_id=user.id, instruction="замени становую на румынскую")
    assert mod_res["name"] == "Массонабор 4 дня (Модифицированный)"
    assert mod_res["plan_data"]["days"][0]["exercises"][0]["name"] == "Румынская тяга"


@pytest.mark.asyncio
async def test_workouts_api(workout_db, user_repo_s9, workout_repo_s9, mock_gemini_s9):
    user = await user_repo_s9.get_or_create_user(telegram_id=9004, timezone="Asia/Almaty")

    food_repo = FoodRepository(workout_db)
    expense_repo = ExpenseRepository(workout_db)
    reminder_repo = ReminderRepository(workout_db)
    prod_repo = ProductivityRepository(workout_db)
    nutrition_service = NutritionService()
    expense_service = ExpenseService(expense_repo)
    reminder_service = ReminderService(reminder_repo)

    setup_dependencies(
        db_manager=workout_db,
        user_repo=user_repo_s9,
        food_repo=food_repo,
        expense_repo=expense_repo,
        reminder_repo=reminder_repo,
        nutrition_service=nutrition_service,
        gemini_service=mock_gemini_s9,
        expense_service=expense_service,
        reminder_service=reminder_service,
        productivity_repo=prod_repo,
        workout_repo=workout_repo_s9,
    )

    app = create_app()
    headers = {"X-Dev-User-Id": str(user.id)}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Log workout
        log_resp = await client.post(
            "/api/workouts/log",
            json={"text": "жим 65x8x3, разводка 14х10х3"},
            headers=headers,
        )
        assert log_resp.status_code == 200
        data = log_resp.json()
        assert data["success"] is True
        assert data["prs_count"] == 2
        assert data["tonnage_kg"] > 0
        assert "Анаболическое окно" in data["reminder_message"]

        # 2. History
        hist_resp = await client.get("/api/workouts/history", headers=headers)
        assert hist_resp.status_code == 200
        assert len(hist_resp.json()) == 2

        # 3. PRs
        prs_resp = await client.get("/api/workouts/prs", headers=headers)
        assert prs_resp.status_code == 200
        assert len(prs_resp.json()) == 2

        # 4. Chart
        chart_resp = await client.get("/api/workouts/exercise/Жим/chart", headers=headers)
        assert chart_resp.status_code == 200
        assert "<svg" in chart_resp.json()["svg_markup"]

        # 5. Progression
        prog_resp = await client.get(
            "/api/workouts/progression?exercise_name=Жим&current_weight=65&success=true",
            headers=headers,
        )
        assert prog_resp.status_code == 200
        assert prog_resp.json()["next_recommended_weight"] == 67.5
