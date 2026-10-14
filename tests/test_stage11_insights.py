import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from app.database.connection import DatabaseManager
from app.database.models import CalorieGoalDB, FoodEntryDB, ExpenseDB
from app.database.repositories.user_repository import UserRepository
from app.database.repositories.food_repository import FoodRepository
from app.database.repositories.expense_repository import ExpenseRepository
from app.database.repositories.reminder_repository import ReminderRepository
from app.database.repositories.productivity_repository import ProductivityRepository
from app.database.repositories.workout_repository import WorkoutRepository
from app.database.repositories.finance_repository import FinanceRepository
from app.database.repositories.insights_repository import InsightsRepository
from app.services.gemini import GeminiService
from app.services.nutrition import NutritionService
from app.services.expenses import ExpenseService
from app.services.reminders import ReminderService
from app.services.unified_scheduler import UnifiedSchedulerService
from app.services.insights import InsightsService
from app.api.deps import setup_dependencies
from app.api.app import create_app


@pytest.fixture
async def insights_db(tmp_path):
    db_file = tmp_path / "test_stage11.db"
    db_manager = DatabaseManager(db_file)
    await db_manager.init_db()
    return db_manager


@pytest.fixture
async def user_repo_s11(insights_db):
    return UserRepository(insights_db)


@pytest.fixture
async def food_repo_s11(insights_db):
    return FoodRepository(insights_db)


@pytest.fixture
async def expense_repo_s11(insights_db):
    return ExpenseRepository(insights_db)


@pytest.fixture
async def productivity_repo_s11(insights_db):
    return ProductivityRepository(insights_db)


@pytest.fixture
async def workout_repo_s11(insights_db):
    return WorkoutRepository(insights_db)


@pytest.fixture
async def finance_repo_s11(insights_db):
    return FinanceRepository(insights_db)


@pytest.fixture
async def insights_repo_s11(insights_db):
    return InsightsRepository(insights_db)


@pytest.fixture
def mock_gemini_s11():
    service = MagicMock(spec=GeminiService)
    service.call_structured = AsyncMock()
    return service


@pytest.fixture
async def insights_service_s11(
    insights_db,
    insights_repo_s11,
    user_repo_s11,
    food_repo_s11,
    expense_repo_s11,
    productivity_repo_s11,
    workout_repo_s11,
    mock_gemini_s11,
):
    return InsightsService(
        db_manager=insights_db,
        insights_repo=insights_repo_s11,
        user_repo=user_repo_s11,
        food_repo=food_repo_s11,
        expense_repo=expense_repo_s11,
        productivity_repo=productivity_repo_s11,
        workout_repo=workout_repo_s11,
        gemini_service=mock_gemini_s11,
    )


# =========================================================================
# 1. 14-DAY DATA READINESS GATE TEST
# =========================================================================

@pytest.mark.asyncio
async def test_insights_data_readiness_gate(insights_service_s11, user_repo_s11, food_repo_s11):
    user = await user_repo_s11.get_or_create_user(telegram_id=11001, timezone="Asia/Almaty")

    # With 0 data days:
    res = await insights_service_s11.audit_user(user.id)
    assert res["status"] == "insufficient_data"
    assert res["days_available"] == 0
    assert res["days_needed"] == 14
    assert "Мало данных" in res["message"]

    # Log 5 days of weights
    for i in range(5):
        d_str = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        await food_repo_s11.log_weight(user.id, 72.0 + i * 0.1, d_str)

    res5 = await insights_service_s11.audit_user(user.id)
    assert res5["status"] == "insufficient_data"
    assert res5["days_available"] == 5
    assert res5["days_needed"] == 14
    assert "нужно ещё 9 дней" in res5["message"]


# =========================================================================
# 2. DETERMINISTIC SQL DETECTORS TEST (>= 14 DAYS)
# =========================================================================

@pytest.mark.asyncio
async def test_deterministic_detectors(
    insights_service_s11,
    insights_db,
    user_repo_s11,
    food_repo_s11,
    workout_repo_s11,
    expense_repo_s11,
):
    user = await user_repo_s11.get_or_create_user(telegram_id=11002, timezone="Asia/Almaty")

    # Set calorie target = 2800 kcal
    await user_repo_s11.save_calorie_goal(
        CalorieGoalDB(
            user_id=user.id,
            bmr=1800,
            tdee=2400,
            target_calories=2800,
            target_protein_g=150,
            target_fat_g=70,
            target_carbs_g=350,
        )
    )

    # Populate 14 days of data with simulated problems:
    # 1) Calorie deficit: eating only 2100 kcal (target 2800 -> 25% deficit)
    # 2) Long meal gaps: breakfast at 09:00, next meal at 15:30 (6.5h gap)
    # 3) Low protein on workout days: workout logged on day 1, 3, 5 with only 60g protein (user 70kg * 1.6 = 112g needed)
    # 4) Weight stall: weights 70.0 kg throughout 14 days (delta 0)
    # 5) Snacks vs Home food: 15,000 KZT on snacks vs 4,000 KZT on groceries
    for i in range(14):
        d_str = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")

        # Weight log: 70.0 kg flat
        await food_repo_s11.log_weight(user.id, 70.0, d_str)

        # Meal 1: 09:00 (1000 kcal, 30g protein)
        entry1 = FoodEntryDB(
            user_id=user.id,
            meal_type="breakfast",
            entry_date=d_str,
            entry_time="09:00",
            total_calories=1000,
            total_protein=30.0,
            total_fat=30.0,
            total_carbs=120.0,
        )
        await food_repo_s11.create_food_entry(entry1)

        # Meal 2: 15:30 (1100 kcal, 30g protein) -> gap 6.5h from 09:00
        entry2 = FoodEntryDB(
            user_id=user.id,
            meal_type="dinner",
            entry_date=d_str,
            entry_time="15:30",
            total_calories=1100,
            total_protein=30.0,
            total_fat=30.0,
            total_carbs=130.0,
        )
        await food_repo_s11.create_food_entry(entry2)

    # Workout logs on 3 days
    for w_day in [1, 3, 5]:
        wd_str = (datetime.utcnow() - timedelta(days=w_day)).strftime("%Y-%m-%d")
        await workout_repo_s11.log_exercise(user.id, wd_str, "Жим лежа", 60.0, 8, 3)

    # Expenses: 15,000 snacks vs 4,000 home food
    await expense_repo_s11.create_expense(
        ExpenseDB(
            user_id=user.id,
            merchant="Магазин",
            amount=15000.0,
            category="snacks",
            description="Чипсы и батончики",
            is_impulse=True,
            expense_date=datetime.utcnow().strftime("%Y-%m-%d"),
        )
    )
    await expense_repo_s11.create_expense(
        ExpenseDB(
            user_id=user.id,
            merchant="Супермаркет",
            amount=4000.0,
            category="groceries",
            description="Гречка и овсянка",
            is_impulse=False,
            expense_date=datetime.utcnow().strftime("%Y-%m-%d"),
        )
    )

    # Run audit!
    audit_res = await insights_service_s11.audit_user(user.id)
    assert audit_res["status"] == "ok"
    assert audit_res["days_available"] >= 14
    findings = audit_res["findings"]
    f_types = [f["finding_type"] for f in findings]

    # Verify all 5 detectors fired
    assert "caloric_deficit_bulking" in f_types
    assert "long_meal_gaps" in f_types
    assert "low_protein_workout_days" in f_types
    assert "weight_stall" in f_types
    assert "snacks_over_home_food" in f_types


# =========================================================================
# 3. WEEKLY ADVICE, ACTION EXECUTION & UNDO
# =========================================================================

@pytest.mark.asyncio
async def test_advice_generation_apply_and_undo(
    insights_db,
    insights_service_s11,
    user_repo_s11,
    productivity_repo_s11,
    food_repo_s11,
):
    user = await user_repo_s11.get_or_create_user(telegram_id=11003, timezone="Asia/Almaty")

    # Initial calorie goal = 2500
    await user_repo_s11.save_calorie_goal(
        CalorieGoalDB(
            user_id=user.id,
            bmr=1700,
            tdee=2200,
            target_calories=2500,
            target_protein_g=140,
            target_fat_g=60,
            target_carbs_g=320,
        )
    )

    # Generate advice (3 cards)
    advice = await insights_service_s11.generate_weekly_advice(user.id)
    assert "id" in advice
    assert len(advice["cards"]) == 3
    advice_id = advice["id"]

    # 1. Test Apply & Undo: Card 1 (increase_calorie_target)
    # Find card with action_type == 'increase_calorie_target'
    c_idx, target_card = next(
        (i, c) for i, c in enumerate(advice["cards"]) if c["action"]["action_type"] == "increase_calorie_target"
    )

    applied_res = await insights_service_s11.apply_advice_action(user.id, advice_id, c_idx)
    assert applied_res["status"] == "applied"

    # Goal should now be 2500 + 200 = 2700 kcal
    updated_goal = await user_repo_s11.get_calorie_goal(user.id)
    assert updated_goal.target_calories == 2700

    # Undo action
    undo_res = await insights_service_s11.undo_advice_action(user.id, advice_id)
    assert undo_res["status"] == "undone"

    # Goal restored to 2500 kcal
    restored_goal = await user_repo_s11.get_calorie_goal(user.id)
    assert restored_goal.target_calories == 2500

    # 2. Test Apply & Undo: Card with schedule_snack_reminder
    s_idx, sched_card = next(
        (i, c) for i, c in enumerate(advice["cards"]) if c["action"]["action_type"] == "schedule_snack_reminder"
    )
    await insights_service_s11.apply_advice_action(user.id, advice_id, s_idx)

    # Check schedule created in DB
    async with insights_db.get_connection() as conn:
        cur = await conn.execute("SELECT * FROM schedules WHERE user_id = ? AND is_active = 1", (user.id,))
        active_reminders = await cur.fetchall()
    assert len(active_reminders) == 1

    # Undo schedule
    await insights_service_s11.undo_advice_action(user.id, advice_id)
    async with insights_db.get_connection() as conn:
        cur = await conn.execute("SELECT * FROM schedules WHERE user_id = ? AND is_active = 1", (user.id,))
        active_reminders_after = await cur.fetchall()
    assert len(active_reminders_after) == 0


# =========================================================================
# 4. TWO-WEEK EFFECT EVALUATION TEST
# =========================================================================

@pytest.mark.asyncio
async def test_advice_effect_evaluation(
    insights_service_s11,
    user_repo_s11,
    food_repo_s11,
    insights_repo_s11,
):
    user = await user_repo_s11.get_or_create_user(telegram_id=11004, timezone="Asia/Almaty")

    advice = await insights_service_s11.generate_weekly_advice(user.id)
    advice_id = advice["id"]

    # Apply advice
    await insights_service_s11.apply_advice_action(user.id, advice_id, 0)

    # Log weight change over 2 weeks: +0.6 kg (70.0 kg -> 70.6 kg)
    d_initial = (datetime.utcnow() - timedelta(days=14)).strftime("%Y-%m-%d")
    d_now = datetime.utcnow().strftime("%Y-%m-%d")
    await food_repo_s11.log_weight(user.id, 70.0, d_initial)
    await food_repo_s11.log_weight(user.id, 70.6, d_now)

    eval_res = await insights_service_s11.evaluate_advice_effect(advice_id)
    assert eval_res is not None
    assert "Совет сработал: +600 г за 2 недели" in eval_res["effect_result"]

    saved_adv = await insights_repo_s11.get_ai_advice_by_id(user.id, advice_id)
    assert saved_adv["effect_result"] == eval_res["effect_result"]


# =========================================================================
# 5. FASTAPI API INTEGRATION TESTS (/api/insights/*)
# =========================================================================

@pytest.mark.asyncio
async def test_insights_api_endpoints(
    insights_db,
    user_repo_s11,
    food_repo_s11,
    expense_repo_s11,
    productivity_repo_s11,
    workout_repo_s11,
    finance_repo_s11,
    insights_repo_s11,
    insights_service_s11,
):
    user = await user_repo_s11.get_or_create_user(telegram_id=11005, timezone="Asia/Almaty")
    reminder_repo = ReminderRepository(insights_db)

    nutrition_service = NutritionService()
    gemini_service = MagicMock(spec=GeminiService)
    expense_service = ExpenseService(expense_repo_s11)
    reminder_service = ReminderService(reminder_repo)
    unified_scheduler = UnifiedSchedulerService(
        productivity_repo=productivity_repo_s11,
        user_repo=user_repo_s11,
        food_repo=food_repo_s11,
    )

    setup_dependencies(
        db_manager=insights_db,
        user_repo=user_repo_s11,
        food_repo=food_repo_s11,
        expense_repo=expense_repo_s11,
        reminder_repo=reminder_repo,
        nutrition_service=nutrition_service,
        gemini_service=gemini_service,
        expense_service=expense_service,
        reminder_service=reminder_service,
        productivity_repo=productivity_repo_s11,
        unified_scheduler_service=unified_scheduler,
        workout_repo=workout_repo_s11,
        finance_repo=finance_repo_s11,
        insights_repo=insights_repo_s11,
        insights_service=insights_service_s11,
    )

    app = create_app()
    headers = {"X-Dev-User-Id": str(user.id)}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Audit endpoint (empty data -> insufficient_data)
        resp_audit = await ac.get("/api/insights/audit", headers=headers)
        assert resp_audit.status_code == 200
        assert resp_audit.json()["status"] == "insufficient_data"

        # 2. Get advice (auto generates fallback cards)
        resp_adv = await ac.get("/api/insights/advice", headers=headers)
        assert resp_adv.status_code == 200
        adv_data = resp_adv.json()
        assert len(adv_data["cards"]) == 3
        advice_id = adv_data["id"]

        # 3. Apply advice action
        resp_apply = await ac.post(
            f"/api/insights/advice/{advice_id}/apply",
            json={"card_index": 1},
            headers=headers,
        )
        assert resp_apply.status_code == 200
        assert resp_apply.json()["status"] == "applied"

        # 4. Undo advice action
        resp_undo = await ac.post(f"/api/insights/advice/{advice_id}/undo", headers=headers)
        assert resp_undo.status_code == 200
        assert resp_undo.json()["status"] == "undone"

        # 5. Evaluate endpoint
        resp_eval = await ac.post(f"/api/insights/advice/{advice_id}/evaluate", headers=headers)
        assert resp_eval.status_code == 200
        assert "effect_result" in resp_eval.json()
