import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from zoneinfo import ZoneInfo

from app.database.connection import DatabaseManager
from app.database.repositories.user_repository import UserRepository
from app.database.repositories.food_repository import FoodRepository
from app.database.repositories.expense_repository import ExpenseRepository
from app.database.repositories.reminder_repository import ReminderRepository
from app.database.repositories.productivity_repository import ProductivityRepository
from app.database.repositories.workout_repository import WorkoutRepository
from app.database.repositories.finance_repository import FinanceRepository
from app.services.gemini import GeminiService
from app.services.nutrition import NutritionService
from app.services.expenses import ExpenseService
from app.services.reminders import ReminderService
from app.services.unified_scheduler import UnifiedSchedulerService
from app.api.deps import setup_dependencies
from app.api.app import create_app


@pytest.fixture
async def finance_db(tmp_path):
    db_file = tmp_path / "test_stage10.db"
    db_manager = DatabaseManager(db_file)
    await db_manager.init_db()
    return db_manager


@pytest.fixture
async def user_repo_s10(finance_db):
    return UserRepository(finance_db)


@pytest.fixture
async def finance_repo_s10(finance_db):
    return FinanceRepository(finance_db)


@pytest.fixture
async def expense_repo_s10(finance_db):
    return ExpenseRepository(finance_db)


@pytest.fixture
async def productivity_repo_s10(finance_db):
    return ProductivityRepository(finance_db)


@pytest.fixture
async def food_repo_s10(finance_db):
    return FoodRepository(finance_db)


# =========================================================================
# 1. SAVINGS GOALS TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_savings_goal_crud_and_forecast(finance_repo_s10, user_repo_s10):
    user = await user_repo_s10.get_or_create_user(telegram_id=10001, timezone="Asia/Almaty")

    # Create goal: На курс масса/спортпит 300,000 KZT, уже есть 50,000, в месяц 50,000
    goal = await finance_repo_s10.create_savings_goal(
        user_id=user.id,
        title="Спортпит и витамины на год",
        target_amount=300000.0,
        current_amount=50000.0,
        monthly_deposit=50000.0,
        currency="₸",
        target_date="2027-04-01",
    )

    assert goal is not None
    assert goal["title"] == "Спортпит и витамины на год"
    assert goal["current_amount"] == 50000.0
    assert goal["target_amount"] == 300000.0
    assert goal["remaining_amount"] == 250000.0
    assert goal["progress_percent"] == 16.7
    assert "█" in goal["progress_bar"]  # progress bar generated
    # 250,000 / 50,000 = 5 months
    assert goal["estimated_months_to_goal"] == 5

    # Deposit 100,000 KZT
    updated = await finance_repo_s10.deposit_to_savings_goal(
        user_id=user.id,
        goal_id=goal["id"],
        amount=100000.0,
    )
    assert updated["current_amount"] == 150000.0
    assert updated["remaining_amount"] == 150000.0
    assert updated["progress_percent"] == 50.0
    assert updated["estimated_months_to_goal"] == 3

    # Delete goal
    deleted = await finance_repo_s10.delete_savings_goal(user_id=user.id, goal_id=goal["id"])
    assert deleted is True

    goals = await finance_repo_s10.get_savings_goals(user_id=user.id)
    assert len(goals) == 0


# =========================================================================
# 2. SUBSCRIPTIONS TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_subscriptions_lifecycle_and_due_detection(finance_repo_s10, user_repo_s10):
    user = await user_repo_s10.get_or_create_user(telegram_id=10002, timezone="Asia/Almaty")

    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    tomorrow_str = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
    next_week_str = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")

    # Sub 1: Яндекс Плюс - due tomorrow
    sub1 = await finance_repo_s10.create_subscription(
        user_id=user.id,
        name="Яндекс Плюс",
        amount=2990.0,
        next_payment_date=tomorrow_str,
        currency="₸",
        billing_cycle="monthly",
    )
    assert sub1["name"] == "Яндекс Плюс"
    assert sub1["is_due_soon"] is True
    assert sub1["days_until_payment"] == 1

    # Sub 2: Spotify - due in 7 days
    sub2 = await finance_repo_s10.create_subscription(
        user_id=user.id,
        name="Spotify",
        amount=2500.0,
        next_payment_date=next_week_str,
        currency="₸",
        billing_cycle="monthly",
    )
    assert sub2["is_due_soon"] is False
    assert sub2["days_until_payment"] == 7

    # Query subscriptions due tomorrow
    due_tomorrow = await finance_repo_s10.get_subscriptions_due_on(tomorrow_str)
    assert len(due_tomorrow) == 1
    assert due_tomorrow[0]["name"] == "Яндекс Плюс"

    # Update next payment date after renewal
    new_date = (datetime.utcnow() + timedelta(days=31)).strftime("%Y-%m-%d")
    updated = await finance_repo_s10.update_subscription_next_date(
        user_id=user.id,
        sub_id=sub1["id"],
        next_payment_date=new_date,
    )
    assert updated is True

    sub1_fresh = await finance_repo_s10.get_subscription_by_id(user.id, sub1["id"])
    assert sub1_fresh["next_payment_date"] == new_date
    assert sub1_fresh["is_due_soon"] is False


# =========================================================================
# 3. DEBTS TESTS (Мне должны / Я должен, partial repay, 1-tap settle)
# =========================================================================

@pytest.mark.asyncio
async def test_debts_totals_repay_and_one_tap_settle(finance_repo_s10, user_repo_s10):
    user = await user_repo_s10.get_or_create_user(telegram_id=10003, timezone="Asia/Almaty")

    # 1. Someone owes me: Дамир занял 15,000 KZT
    d1 = await finance_repo_s10.create_debt(
        user_id=user.id,
        person_name="Дамир",
        amount=15000.0,
        direction="they_owe",
        currency="₸",
        description="За спортзал",
    )

    # 2. I owe someone: Должен Тимуру 5,000 KZT
    d2 = await finance_repo_s10.create_debt(
        user_id=user.id,
        person_name="Тимур",
        amount=5000.0,
        direction="i_owe",
        currency="₸",
        description="За обед",
    )

    debts_state = await finance_repo_s10.get_debts(user_id=user.id, is_settled=False)
    assert debts_state["total_they_owe"] == 15000.0
    assert debts_state["total_i_owe"] == 5000.0
    assert debts_state["net_balance"] == 10000.0  # +10,000 KZT net in my favor

    # Partial repayment: Дамир вернул 5,000 KZT
    repaid = await finance_repo_s10.partial_repay_debt(
        user_id=user.id,
        debt_id=d1["id"],
        repay_amount=5000.0,
    )
    assert repaid["amount"] == 10000.0
    assert repaid["is_settled"] is False

    # 1-Tap Settle: Закрыть долг Тимуру в 1 тап
    settled = await finance_repo_s10.settle_debt_one_tap(
        user_id=user.id,
        debt_id=d2["id"],
    )
    assert settled["is_settled"] is True
    assert settled["amount"] == 0.0

    debts_after = await finance_repo_s10.get_debts(user_id=user.id, is_settled=False)
    assert debts_after["total_they_owe"] == 10000.0
    assert debts_after["total_i_owe"] == 0.0
    assert debts_after["net_balance"] == 10000.0


# =========================================================================
# 4. FASTAPI API INTEGRATION TESTS (/api/finances/*)
# =========================================================================

@pytest.mark.asyncio
async def test_finances_api_endpoints(
    finance_db,
    user_repo_s10,
    food_repo_s10,
    expense_repo_s10,
    productivity_repo_s10,
    finance_repo_s10,
):
    user = await user_repo_s10.get_or_create_user(telegram_id=10004, timezone="Asia/Almaty")
    reminder_repo = ReminderRepository(finance_db)
    workout_repo = WorkoutRepository(finance_db)

    nutrition_service = NutritionService()
    gemini_service = MagicMock(spec=GeminiService)
    expense_service = ExpenseService(expense_repo_s10)
    reminder_service = ReminderService(reminder_repo)
    unified_scheduler = UnifiedSchedulerService(
        productivity_repo=productivity_repo_s10,
        user_repo=user_repo_s10,
        food_repo=food_repo_s10,
    )

    setup_dependencies(
        db_manager=finance_db,
        user_repo=user_repo_s10,
        food_repo=food_repo_s10,
        expense_repo=expense_repo_s10,
        reminder_repo=reminder_repo,
        nutrition_service=nutrition_service,
        gemini_service=gemini_service,
        expense_service=expense_service,
        reminder_service=reminder_service,
        productivity_repo=productivity_repo_s10,
        unified_scheduler_service=unified_scheduler,
        workout_repo=workout_repo,
        finance_repo=finance_repo_s10,
    )

    app = create_app()
    headers = {"X-Dev-User-Id": str(user.id)}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Create Savings Goal
        resp_s = await ac.post(
            "/api/finances/savings",
            json={"title": "Поездка", "target_amount": 200000, "current_amount": 40000, "monthly_deposit": 20000},
            headers=headers,
        )
        assert resp_s.status_code == 200
        s_data = resp_s.json()
        assert s_data["progress_percent"] == 20.0

        # Deposit to Savings Goal
        resp_dep = await ac.post(
            f"/api/finances/savings/{s_data['id']}/deposit",
            json={"amount": 10000},
            headers=headers,
        )
        assert resp_dep.status_code == 200
        assert resp_dep.json()["current_amount"] == 50000

        # Create Subscription
        resp_sub = await ac.post(
            "/api/finances/subscriptions",
            json={"name": "Netflix", "amount": 4500, "next_payment_date": "2026-11-01"},
            headers=headers,
        )
        assert resp_sub.status_code == 200

        # Create Debt
        resp_d = await ac.post(
            "/api/finances/debts",
            json={"person_name": "Арман", "amount": 8000, "direction": "they_owe", "description": "Пицца"},
            headers=headers,
        )
        assert resp_d.status_code == 200
        d_id = resp_d.json()["id"]

        # Unified Overview
        resp_ov = await ac.get("/api/finances/overview", headers=headers)
        assert resp_ov.status_code == 200
        ov_data = resp_ov.json()
        assert ov_data["savings"]["goals_count"] == 1
        assert ov_data["savings"]["total_saved"] == 50000
        assert ov_data["subscriptions"]["count"] == 1
        assert ov_data["subscriptions"]["monthly_burn"] == 4500
        assert ov_data["debts"]["total_they_owe"] == 8000
        assert ov_data["debts"]["net_balance"] == 8000

        # Settle Debt in 1 tap
        resp_settle = await ac.post(f"/api/finances/debts/{d_id}/settle", headers=headers)
        assert resp_settle.status_code == 200
        assert resp_settle.json()["is_settled"] is True


# =========================================================================
# 5. SCHEDULER ADVANCE SUBSCRIPTION ALERT TEST
# =========================================================================

@pytest.mark.asyncio
async def test_scheduler_subscription_advance_alert(
    finance_db,
    user_repo_s10,
    food_repo_s10,
    productivity_repo_s10,
    finance_repo_s10,
):
    user = await user_repo_s10.get_or_create_user(telegram_id=10005, timezone="Asia/Almaty")

    tz = ZoneInfo("Asia/Almaty")
    now_dt = datetime.now(tz=tz)
    now_ts = int(now_dt.timestamp())
    tomorrow_str = (now_dt + timedelta(days=1)).date().isoformat()

    # Create sub due tomorrow
    await finance_repo_s10.create_subscription(
        user_id=user.id,
        name="Яндекс Плюс",
        amount=2990.0,
        next_payment_date=tomorrow_str,
        currency="₸",
        billing_cycle="monthly",
    )

    mock_bot = AsyncMock()
    scheduler = UnifiedSchedulerService(
        productivity_repo=productivity_repo_s10,
        user_repo=user_repo_s10,
        food_repo=food_repo_s10,
        bot=mock_bot,
    )

    # Run check
    await scheduler._run_subscription_checks(now_ts)

    # Verify message sent to user.telegram_id
    mock_bot.send_message.assert_called_once()
    call_args = mock_bot.send_message.call_args
    assert call_args.kwargs["chat_id"] == 10005
    assert "Яндекс Плюс" in call_args.kwargs["text"]
    assert "2 990 ₸" in call_args.kwargs["text"]
    assert "Завтра списание" in call_args.kwargs["text"]

    # Second run at same time should not duplicate (idempotent deduplication)
    mock_bot.send_message.reset_mock()
    await scheduler._run_subscription_checks(now_ts)
    mock_bot.send_message.assert_not_called()
