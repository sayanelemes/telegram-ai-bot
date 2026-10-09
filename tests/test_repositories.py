import pytest
from app.database.models import (
    UserProfileDB,
    CalorieGoalDB,
    FoodEntryDB,
    FoodItemDB,
    ExpenseDB,
    ExpenseItemDB,
    ReminderDB,
)


@pytest.mark.asyncio
async def test_user_repository(user_repo):
    # 1. Create user
    user = await user_repo.get_or_create_user(
        telegram_id=123456,
        username="alex",
        first_name="Alex",
        timezone="Asia/Almaty"
    )
    assert user.id is not None
    assert user.telegram_id == 123456
    assert user.timezone == "Asia/Almaty"

    # 2. Get existing user
    fetched = await user_repo.get_by_telegram_id(123456)
    assert fetched.id == user.id

    # 3. Update timezone
    await user_repo.update_timezone(user.id, "Europe/Moscow")
    updated = await user_repo.get_by_id(user.id)
    assert updated.timezone == "Europe/Moscow"

    # 4. Save and fetch profile
    profile = UserProfileDB(
        user_id=user.id,
        gender="male",
        age=25,
        height_cm=180.0,
        weight_kg=80.0,
        activity_level="moderate",
        goal="loss"
    )
    saved_prof = await user_repo.save_profile(profile)
    assert saved_prof.id is not None

    fetched_prof = await user_repo.get_profile(user.id)
    assert fetched_prof.weight_kg == 80.0
    assert fetched_prof.goal == "loss"

    # 5. Save and fetch calorie goal
    goal = CalorieGoalDB(
        user_id=user.id,
        bmr=1805,
        tdee=2797,
        target_calories=2200,
        target_protein_g=160,
        target_fat_g=70,
        target_carbs_g=230
    )
    saved_goal = await user_repo.save_calorie_goal(goal)
    assert saved_goal.id is not None

    fetched_goal = await user_repo.get_calorie_goal(user.id)
    assert fetched_goal.target_calories == 2200


@pytest.mark.asyncio
async def test_food_repository(user_repo, food_repo):
    user = await user_repo.get_or_create_user(telegram_id=99999, first_name="Tester")

    # Add meal entry
    entry = FoodEntryDB(
        user_id=user.id,
        meal_type="Обед",
        entry_date="2026-10-08",
        entry_time="13:30",
        total_calories=550,
        total_protein=40.0,
        total_fat=15.0,
        total_carbs=60.0,
        advice="Хороший обед",
        items=[
            FoodItemDB(name="Курица", portion_g=150, calories=250, protein_g=35.0, fat_g=5.0, carbs_g=0.0),
            FoodItemDB(name="Гречка", portion_g=150, calories=300, protein_g=5.0, fat_g=10.0, carbs_g=60.0),
        ]
    )
    created = await food_repo.create_food_entry(entry)
    assert created.id is not None
    assert len(created.items) == 2

    # Get by id
    fetched = await food_repo.get_entry_by_id(created.id)
    assert fetched.total_calories == 550
    assert len(fetched.items) == 2

    # Get daily totals
    totals = await food_repo.get_daily_totals(user.id, "2026-10-08")
    assert totals["count"] == 1
    assert totals["calories"] == 550
    assert totals["protein"] == 40.0

    # History
    history = await food_repo.get_history_by_dates(user.id, limit_days=7)
    assert len(history) == 1
    assert history[0]["date"] == "2026-10-08"

    # Count history days
    count = await food_repo.count_history_days(user.id)
    assert count == 1


@pytest.mark.asyncio
async def test_expense_repository(user_repo, expense_repo):
    user = await user_repo.get_or_create_user(telegram_id=88888, first_name="FinanceUser")

    expense = ExpenseDB(
        user_id=user.id,
        merchant="Magnum",
        amount=5000.0,
        currency="₸",
        category="food",
        description="Продукты на неделю",
        expense_date="2026-10-08",
        items=[
            ExpenseItemDB(name="Мясо", price=3500.0, quantity=1.0),
            ExpenseItemDB(name="Овощи", price=1500.0, quantity=1.0),
        ]
    )
    saved = await expense_repo.create_expense(expense)
    assert saved.id is not None
    assert len(saved.items) == 2

    # Daily total
    daily_total = await expense_repo.get_daily_total(user.id, "2026-10-08")
    assert daily_total == 5000.0

    # Period categories
    cats = await expense_repo.get_period_categories(user.id, "2026-10-01", "2026-10-31")
    assert len(cats) == 1
    assert cats[0]["category"] == "food"
    assert cats[0]["total"] == 5000.0


@pytest.mark.asyncio
async def test_reminder_repository(user_repo, reminder_repo):
    user = await user_repo.get_or_create_user(telegram_id=77777, first_name="ReminderUser")

    reminder = ReminderDB(
        user_id=user.id,
        reminder_type="breakfast",
        time_str="09:00",
        interval_hours=0,
        is_enabled=True,
    )
    saved = await reminder_repo.save_reminder(reminder)
    assert saved.id is not None

    # Toggle off
    await reminder_repo.toggle_reminder(user.id, "breakfast", False)
    fetched = await reminder_repo.get_reminder(user.id, "breakfast")
    assert fetched.is_enabled is False

    # Update time
    await reminder_repo.update_reminder_time(user.id, "breakfast", "08:30")
    updated = await reminder_repo.get_reminder(user.id, "breakfast")
    assert updated.time_str == "08:30"
