import asyncio
import json
import pytest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, MagicMock

from app.database.connection import DatabaseManager
from app.database.repositories.user_repository import UserRepository
from app.database.repositories.food_repository import FoodRepository
from app.database.repositories.productivity_repository import ProductivityRepository
from app.services.unified_scheduler import UnifiedSchedulerService
from app.api.deps import setup_dependencies
from httpx import AsyncClient, ASGITransport
from app.api.app import create_app


@pytest.fixture
async def prod_db(tmp_path):
    db_file = tmp_path / "test_stage8.db"
    db_manager = DatabaseManager(db_file)
    await db_manager.init_db()
    return db_manager


@pytest.fixture
async def user_repo_s8(prod_db):
    return UserRepository(prod_db)


@pytest.fixture
async def food_repo_s8(prod_db):
    return FoodRepository(prod_db)


@pytest.fixture
async def prod_repo_s8(prod_db):
    return ProductivityRepository(prod_db)


@pytest.fixture
def mock_bot_s8():
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=999))
    return bot


@pytest.mark.asyncio
async def test_tasks_postpone_and_warning(prod_repo_s8, user_repo_s8):
    user = await user_repo_s8.get_or_create_user(telegram_id=8001, timezone="Asia/Almaty")

    # Create task
    task = await prod_repo_s8.create_task(user.id, "Купить творог и бананы", priority="high")
    assert task["postponed_count"] == 0

    # 1st postpone: tomorrow
    p1 = await prod_repo_s8.postpone_task(user.id, task["id"], "tomorrow", "Asia/Almaty")
    assert p1["postponed_count"] == 1
    assert p1["warning"] is None

    # 2nd postpone: evening
    p2 = await prod_repo_s8.postpone_task(user.id, task["id"], "evening", "Asia/Almaty")
    assert p2["postponed_count"] == 2
    assert p2["warning"] is None

    # 3rd postpone: saturday -> warning triggered!
    p3 = await prod_repo_s8.postpone_task(user.id, task["id"], "saturday", "Asia/Almaty")
    assert p3["postponed_count"] == 3
    assert p3["warning"] == "Удалить или разбить?"


@pytest.mark.asyncio
async def test_notes_search_and_pin(prod_repo_s8, user_repo_s8):
    user = await user_repo_s8.get_or_create_user(telegram_id=8002, timezone="Asia/Almaty")

    await prod_repo_s8.create_note(user.id, "Список покупок", "Творог, яйца, рис", tags="еда,зал", is_pinned=False)
    n2 = await prod_repo_s8.create_note(user.id, "Тренировочный сплит", "Пн: грудь, Ср: спина", tags="зал", is_pinned=True)

    # Pinned first
    all_notes = await prod_repo_s8.get_notes(user.id)
    assert len(all_notes) == 2
    assert all_notes[0]["id"] == n2["id"]  # pinned comes first

    # Search query
    found = await prod_repo_s8.get_notes(user.id, query="рис")
    assert len(found) == 1
    assert "Творог" in found[0]["content"]

    # Filter by tag
    food_notes = await prod_repo_s8.get_notes(user.id, tag="еда")
    assert len(food_notes) == 1


@pytest.mark.asyncio
async def test_habits_streak_and_threat(prod_repo_s8, user_repo_s8):
    user = await user_repo_s8.get_or_create_user(telegram_id=8003, timezone="Asia/Almaty")
    today = "2026-10-14"

    h1 = await prod_repo_s8.create_habit(user.id, "Выпить 2.5л воды")
    h2 = await prod_repo_s8.create_habit(user.id, "Съесть 150г белка")

    # Initially both are pending threats
    threats = await prod_repo_s8.get_pending_habits_for_today(user.id, today)
    assert len(threats) == 2

    # Toggle h1 completed
    res = await prod_repo_s8.toggle_habit_log(user.id, h1["id"], today)
    assert res["is_completed_today"] is True
    assert res["streak"] == 1
    assert res["best_streak"] == 1

    # Now only h2 is threat
    threats_after = await prod_repo_s8.get_pending_habits_for_today(user.id, today)
    assert len(threats_after) == 1
    assert threats_after[0]["id"] == h2["id"]


@pytest.mark.asyncio
async def test_user_modes_suppression(prod_repo_s8, user_repo_s8):
    user = await user_repo_s8.get_or_create_user(telegram_id=8004, timezone="Asia/Almaty")

    # Set DND for 4 hours
    until = (datetime.utcnow() + timedelta(hours=4)).isoformat()
    await prod_repo_s8.set_mode(user.id, "dnd", until)

    modes = await prod_repo_s8.get_active_modes(user.id)
    assert modes["dnd"] is True
    assert modes["sick"] is False

    # Clear
    cleared = await prod_repo_s8.clear_modes(user.id)
    modes2 = await prod_repo_s8.get_active_modes(user.id)
    assert modes2["dnd"] is False


@pytest.mark.asyncio
async def test_unified_scheduler_hunger_detector(prod_repo_s8, user_repo_s8, food_repo_s8, mock_bot_s8):
    from app.database.models import CalorieGoalDB
    user = await user_repo_s8.get_or_create_user(telegram_id=8005, timezone="Asia/Almaty")
    await user_repo_s8.save_calorie_goal(
        CalorieGoalDB(
            user_id=user.id,
            bmr=1800,
            tdee=2500,
            target_calories=3000,
            target_protein_g=160,
            target_fat_g=80,
            target_carbs_g=360,
        )
    )

    svc = UnifiedSchedulerService(
        productivity_repo=prod_repo_s8,
        user_repo=user_repo_s8,
        food_repo=food_repo_s8,
        bot=mock_bot_s8,
    )

    # 1. Daytime 12:00 UTC (17:00 Almaty), 0 meals logged -> trigger hunger alert!
    fake_now = int(datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc).timestamp())
    triggered = await svc.check_hunger_for_user(user.id, fake_now)
    assert triggered is True
    assert mock_bot_s8.send_message.call_count == 1
    call_args = mock_bot_s8.send_message.call_args[1]
    assert "Пора подкрепиться" in call_args["text"]
    assert "3000 ккал" in call_args["text"]

    # 2. Same time within 2 hours cooldown -> should NOT trigger again
    triggered_cooldown = await svc.check_hunger_for_user(user.id, fake_now + 1800)
    assert triggered_cooldown is False

    # 3. Sick mode -> should NOT trigger
    sick_until = (datetime.utcnow() + timedelta(days=2)).isoformat()
    await prod_repo_s8.set_mode(user.id, "sick", sick_until)
    # Simulate 3 hours later
    triggered_sick = await svc.check_hunger_for_user(user.id, fake_now + 3 * 3600)
    assert triggered_sick is False


@pytest.mark.asyncio
async def test_morning_and_evening_summaries(prod_repo_s8, user_repo_s8, food_repo_s8):
    from app.database.models import CalorieGoalDB
    user = await user_repo_s8.get_or_create_user(telegram_id=8006, timezone="Asia/Almaty")
    await user_repo_s8.save_calorie_goal(
        CalorieGoalDB(
            user_id=user.id,
            bmr=1700,
            tdee=2300,
            target_calories=2800,
            target_protein_g=160,
            target_fat_g=80,
            target_carbs_g=340,
        )
    )

    # Add weight logs
    await food_repo_s8.log_weight(user.id, 75.0, "2026-10-13")
    await food_repo_s8.log_weight(user.id, 75.4, "2026-10-14")

    # Add urgent task
    await prod_repo_s8.create_task(user.id, "Тяжёлый присед 100 кг", priority="high")

    svc = UnifiedSchedulerService(
        productivity_repo=prod_repo_s8,
        user_repo=user_repo_s8,
        food_repo=food_repo_s8,
    )

    morning = await svc.build_morning_summary(user.id)
    assert "75.4 кг" in morning
    assert "+0.4 кг со вчера" in morning
    assert "2800 ккал" in morning
    assert "Тяжёлый присед 100 кг" in morning

    evening = await svc.build_evening_checkout(user.id)
    assert "Вечерний чекаут" in evening
    assert "Нехватка:" in evening and "2800 ккал" in evening
    assert "Оцени уровень сытости" in evening


@pytest.mark.asyncio
async def test_schedules_tick_and_snooze(prod_repo_s8, user_repo_s8, food_repo_s8, mock_bot_s8):
    user = await user_repo_s8.get_or_create_user(telegram_id=8007, timezone="Asia/Almaty")

    svc = UnifiedSchedulerService(
        productivity_repo=prod_repo_s8,
        user_repo=user_repo_s8,
        food_repo=food_repo_s8,
        bot=mock_bot_s8,
    )

    now_ts = int(datetime.utcnow().timestamp())
    # Add reminder schedule due right now
    s_id = await prod_repo_s8.save_schedule(
        user_id=user.id,
        job_type="reminder",
        scheduled_time="now",
        next_run_at=now_ts - 10,
        data_json=json.dumps({"text": "Выпей протеиновый коктейль!"}),
    )

    # Execute tick
    processed = await svc.tick(now_ts)
    assert len(processed) >= 1
    assert any(p.get("schedule_id") == s_id for p in processed)
    assert mock_bot_s8.send_message.call_count >= 1

    # Snooze schedule by 15 mins
    new_time = await svc.snooze(s_id, 15, now_ts)
    assert new_time == now_ts + 15 * 60


@pytest.mark.asyncio
async def test_api_tasks_and_checkins(prod_db, user_repo_s8, food_repo_s8, prod_repo_s8):
    from app.database.repositories.expense_repository import ExpenseRepository
    from app.database.repositories.reminder_repository import ReminderRepository
    from app.services.nutrition import NutritionService
    from app.services.gemini import GeminiService
    from app.services.expenses import ExpenseService
    from app.services.reminders import ReminderService

    user = await user_repo_s8.get_or_create_user(telegram_id=8008, timezone="Asia/Almaty")

    expense_repo = ExpenseRepository(prod_db)
    reminder_repo = ReminderRepository(prod_db)
    nutrition_service = NutritionService()
    gemini_service = GeminiService(api_key="mock", model_name="gemini")
    expense_service = ExpenseService(expense_repo)
    reminder_service = ReminderService(reminder_repo)

    setup_dependencies(
        db_manager=prod_db,
        user_repo=user_repo_s8,
        food_repo=food_repo_s8,
        expense_repo=expense_repo,
        reminder_repo=reminder_repo,
        nutrition_service=nutrition_service,
        gemini_service=gemini_service,
        expense_service=expense_service,
        reminder_service=reminder_service,
        productivity_repo=prod_repo_s8,
    )

    app = create_app()
    headers = {"X-Dev-User-Id": str(user.id)}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create Task
        t_resp = await client.post(
            "/api/tasks",
            json={"title": "Потренироваться в 18:00", "priority": "high"},
            headers=headers,
        )
        assert t_resp.status_code == 200
        t_data = t_resp.json()
        assert t_data["title"] == "Потренироваться в 18:00"

        # Postpone
        postpone_resp = await client.post(
            f"/api/tasks/{t_data['id']}/postpone",
            json={"choice": "tomorrow"},
            headers=headers,
        )
        assert postpone_resp.status_code == 200
        assert postpone_resp.json()["postponed_count"] == 1

        # Submit Check-in
        ci_resp = await client.post(
            "/api/checkins",
            json={"mood": 4, "energy": 4, "satiety": 5, "notes": "Отличный профицит!"},
            headers=headers,
        )
        assert ci_resp.status_code == 200
        assert ci_resp.json()["satiety"] == 5

        # Today checkin
        today_resp = await client.get("/api/checkins/today", headers=headers)
        assert today_resp.status_code == 200
        assert today_resp.json()["satiety"] == 5

        # Morning summary API
        ms_resp = await client.get("/api/stats/morning-summary", headers=headers)
        assert ms_resp.status_code == 200
        assert "Утренняя сводка" in ms_resp.json()["summary_text"]
