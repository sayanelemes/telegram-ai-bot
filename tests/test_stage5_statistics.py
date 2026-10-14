import pytest
import hmac
import hashlib
import json
from urllib.parse import urlencode
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from httpx import AsyncClient, ASGITransport

from app.database.models import (
    CalorieGoalDB,
    FoodEntryDB,
    FoodItemDB,
    ExpenseDB,
)


def make_valid_init_data(bot_token: str, user_id: int = 9201, first_name: str = "TestStatsUser") -> str:
    user_data = json.dumps({"id": user_id, "first_name": first_name}, separators=(",", ":"))
    params = {
        "auth_date": "1700000000",
        "query_id": "AAHdF6IQAAAAAN0XohD8X8cR",
        "user": user_data,
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    hash_val = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    params["hash"] = hash_val
    return urlencode(params)


@pytest.mark.asyncio
async def test_nutrition_stats_and_bulking_risk(app_instance, user_repo, food_repo, test_settings):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 9201
        auth_header = make_valid_init_data(test_settings.BOT_TOKEN, user_id, "StatsUser")
        headers = {"X-Telegram-Init-Data": auth_header}

        user = await user_repo.get_or_create_user(telegram_id=user_id)
        # Goal: 3000 kcal (bulking target)
        await user_repo.save_calorie_goal(CalorieGoalDB(
            user_id=user.id,
            bmr=1800,
            tdee=2700,
            target_calories=3000,
            target_protein_g=160,
            target_fat_g=90,
            target_carbs_g=380
        ))

        today = datetime.now(ZoneInfo(user.timezone)).date()
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)

        # Day 1 (two days ago): 3200 kcal -> SURPLUS
        await food_repo.create_food_entry(FoodEntryDB(
            user_id=user.id,
            meal_type="dinner",
            entry_date=two_days_ago.strftime("%Y-%m-%d"),
            entry_time="20:00",
            total_calories=3200,
            total_protein=170.0,
            total_fat=95.0,
            total_carbs=410.0,
            items=[FoodItemDB(name="Стейк с рисом", portion_g=600, calories=3200, protein_g=170, fat_g=95, carbs_g=410)]
        ))

        # Day 2 (yesterday): 2400 kcal (< 90% of 3000 = 2700) -> RISK FOR BULKING!
        await food_repo.create_food_entry(FoodEntryDB(
            user_id=user.id,
            meal_type="lunch",
            entry_date=yesterday.strftime("%Y-%m-%d"),
            entry_time="14:00",
            total_calories=2400,
            total_protein=120.0,
            total_fat=70.0,
            total_carbs=300.0,
            items=[FoodItemDB(name="Обед", portion_g=500, calories=2400, protein_g=120, fat_g=70, carbs_g=300)]
        ))

        # Request weekly nutrition stats
        res = await client.get("/api/stats/nutrition?period=week", headers=headers)
        assert res.status_code == 200
        data = res.json()

        assert data["period"] == "week"
        assert data["target_calories"] == 3000
        assert data["total_calories"] >= 5600
        assert data["surplus_days_count"] >= 1
        assert data["risk_days_count"] >= 1

        # Check day-by-day records
        day_two_ago = next((d for d in data["days"] if d["date"] == two_days_ago.strftime("%Y-%m-%d")), None)
        assert day_two_ago is not None
        assert day_two_ago["calories"] == 3200
        assert day_two_ago["is_surplus"] is True
        assert day_two_ago["is_risk"] is False

        day_yesterday = next((d for d in data["days"] if d["date"] == yesterday.strftime("%Y-%m-%d")), None)
        assert day_yesterday is not None
        assert day_yesterday["calories"] == 2400
        assert day_yesterday["is_risk"] is True
        assert day_yesterday["is_surplus"] is False


@pytest.mark.asyncio
async def test_expense_stats_average_check_top_categories_recurring(app_instance, user_repo, expense_repo, test_settings):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 9202
        auth_header = make_valid_init_data(test_settings.BOT_TOKEN, user_id, "ExpenseStatsUser")
        headers = {"X-Telegram-Init-Data": auth_header}

        user = await user_repo.get_or_create_user(telegram_id=user_id)
        today_str = datetime.now(ZoneInfo(user.timezone)).strftime("%Y-%m-%d")

        # Create multiple expenses
        # 1. Food: 3000
        await expense_repo.create_expense(ExpenseDB(
            user_id=user.id,
            merchant="Magnum",
            amount=3000.0,
            category="food",
            expense_date=today_str,
            items=[]
        ))
        # 2. Food: 5000
        await expense_repo.create_expense(ExpenseDB(
            user_id=user.id,
            merchant="Magnum",
            amount=5000.0,
            category="food",
            expense_date=today_str,
            items=[]
        ))
        # 3. Transport: 2000
        await expense_repo.create_expense(ExpenseDB(
            user_id=user.id,
            merchant="Yandex Taxi",
            amount=2000.0,
            category="transport",
            expense_date=today_str,
            items=[]
        ))
        # 4. Entertainment: 1000
        await expense_repo.create_expense(ExpenseDB(
            user_id=user.id,
            merchant="Cinema",
            amount=1000.0,
            category="entertainment",
            expense_date=today_str,
            items=[]
        ))
        # 5. Recurring payment: Spotify 1500 (occurred twice)
        await expense_repo.create_expense(ExpenseDB(
            user_id=user.id,
            merchant="Spotify",
            amount=1500.0,
            category="utilities",
            expense_date=today_str,
            items=[]
        ))
        await expense_repo.create_expense(ExpenseDB(
            user_id=user.id,
            merchant="Spotify",
            amount=1500.0,
            category="utilities",
            expense_date=today_str,
            items=[]
        ))

        # Total expenses = 3000+5000+2000+1000+1500+1500 = 14000
        # Count = 6
        # Average check = 14000 / 6 = 2333.33
        res = await client.get("/api/stats/expenses?period=month", headers=headers)
        assert res.status_code == 200
        data = res.json()

        assert data["total_spent"] == 14000.0
        assert data["total_count"] == 6
        assert abs(data["average_check"] - 2333.33) < 0.1

        # Top 3 categories:
        # food: 8000 (57.1%)
        # utilities: 3000 (21.4%)
        # transport: 2000 (14.3%)
        top_cats = data["top_categories"]
        assert len(top_cats) <= 3
        assert top_cats[0]["category"] == "food"
        assert top_cats[0]["total"] == 8000.0
        assert top_cats[1]["category"] == "utilities"
        assert top_cats[1]["total"] == 3000.0
        assert top_cats[2]["category"] == "transport"
        assert top_cats[2]["total"] == 2000.0

        # Recurring expenses: Spotify appears 2 times
        recurring = data["recurring_expenses"]
        assert len(recurring) >= 1
        spotify_rec = next((r for r in recurring if "spotify" in r["merchant"].lower()), None)
        assert spotify_rec is not None
        assert spotify_rec["occurrences"] >= 2
        assert spotify_rec["amount"] == 1500.0


@pytest.mark.asyncio
async def test_category_limits_and_alert_thresholds(app_instance, user_repo, expense_repo, test_settings):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 9203
        auth_header = make_valid_init_data(test_settings.BOT_TOKEN, user_id, "BudgetLimitUser")
        headers = {"X-Telegram-Init-Data": auth_header}

        await user_repo.get_or_create_user(telegram_id=user_id)

        # Set limit for 'food': 10 000 KZT
        set_res = await client.post(
            "/api/expenses/category-limits",
            headers=headers,
            json={"category": "food", "monthly_limit": 10000.0}
        )
        assert set_res.status_code == 200
        assert set_res.json()["monthly_limit"] == 10000.0

        # Expense 1: 5 000 KZT (50% -> No alert)
        exp1 = await client.post(
            "/api/expenses",
            headers=headers,
            json={"merchant": "Cafe", "amount": 5000.0, "category": "food", "items": []}
        )
        assert exp1.status_code == 200
        assert exp1.json()["alert"] is None

        # Expense 2: 3 500 KZT (Total 8 500 = 85% -> 80% ALERT triggered!)
        exp2 = await client.post(
            "/api/expenses",
            headers=headers,
            json={"merchant": "Dinner", "amount": 3500.0, "category": "food", "items": []}
        )
        assert exp2.status_code == 200
        assert exp2.json()["alert"] is not None
        assert "достигла 85.0%" in exp2.json()["alert"]

        # Expense 3: 500 KZT (Total 9 000 = 90% -> 80% already sent, 100% not reached -> No alert!)
        exp3 = await client.post(
            "/api/expenses",
            headers=headers,
            json={"merchant": "Snack", "amount": 500.0, "category": "food", "items": []}
        )
        assert exp3.status_code == 200
        assert exp3.json()["alert"] is None

        # Expense 4: 1 500 KZT (Total 10 500 = 105% -> 100% ALERT triggered!)
        exp4 = await client.post(
            "/api/expenses",
            headers=headers,
            json={"merchant": "Groceries", "amount": 1500.0, "category": "food", "items": []}
        )
        assert exp4.status_code == 200
        assert exp4.json()["alert"] is not None
        assert "100%" in exp4.json()["alert"]

        # Expense 5: 1 000 KZT (Total 11 500 = 115% -> 100% already sent -> No alert!)
        exp5 = await client.post(
            "/api/expenses",
            headers=headers,
            json={"merchant": "Dessert", "amount": 1000.0, "category": "food", "items": []}
        )
        assert exp5.status_code == 200
        assert exp5.json()["alert"] is None

        # Check limits list endpoint
        limits_res = await client.get("/api/expenses/category-limits", headers=headers)
        assert limits_res.status_code == 200
        limits_data = limits_res.json()
        assert len(limits_data) >= 1
        food_limit = next(item for item in limits_data if item["category"] == "food")
        assert food_limit["monthly_limit"] == 10000.0
        assert food_limit["spent"] == 11500.0
        assert food_limit["alert_80_sent"] is True
        assert food_limit["alert_100_sent"] is True

        # Delete limit
        del_res = await client.delete("/api/expenses/category-limits/food", headers=headers)
        assert del_res.status_code == 200
        assert del_res.json()["success"] is True


@pytest.mark.asyncio
async def test_csv_export(app_instance, user_repo, expense_repo, test_settings):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 9204
        auth_header = make_valid_init_data(test_settings.BOT_TOKEN, user_id, "CsvExportUser")
        headers = {"X-Telegram-Init-Data": auth_header}

        user = await user_repo.get_or_create_user(telegram_id=user_id)
        today_str = datetime.now(ZoneInfo(user.timezone)).strftime("%Y-%m-%d")

        await expense_repo.create_expense(ExpenseDB(
            user_id=user.id,
            merchant="Супермаркет",
            amount=4200.50,
            currency="₸",
            category="food",
            description="Продукты на неделю",
            is_impulsive=False,
            expense_date=today_str,
            items=[]
        ))

        res = await client.get("/api/expenses/export/csv", headers=headers)
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/csv")
        assert 'attachment; filename="expenses.csv"' in res.headers["content-disposition"]

        content = res.text
        # Check UTF-8 BOM
        assert content.startswith("\ufeff")
        assert "Супермаркет" in content
        assert "4200.50" in content
        assert "Продукты на неделю" in content


@pytest.mark.asyncio
async def test_sunday_weekly_summary(app_instance, user_repo, food_repo, expense_repo, test_settings):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 9205
        auth_header = make_valid_init_data(test_settings.BOT_TOKEN, user_id, "SundaySummaryUser")
        headers = {"X-Telegram-Init-Data": auth_header}

        user = await user_repo.get_or_create_user(telegram_id=user_id)
        await user_repo.save_calorie_goal(CalorieGoalDB(
            user_id=user.id,
            bmr=1700,
            tdee=2500,
            target_calories=2800,
            target_protein_g=150,
            target_fat_g=80,
            target_carbs_g=350
        ))

        today_str = datetime.now(ZoneInfo(user.timezone)).strftime("%Y-%m-%d")

        # Food: 2900 kcal today (surplus)
        await food_repo.create_food_entry(FoodEntryDB(
            user_id=user.id,
            meal_type="dinner",
            entry_date=today_str,
            entry_time="20:00",
            total_calories=2900,
            total_protein=160.0,
            total_fat=85.0,
            total_carbs=360.0,
            items=[]
        ))

        # Normal expense: 5000
        await expense_repo.create_expense(ExpenseDB(
            user_id=user.id,
            merchant="Продукты",
            amount=5000.0,
            category="food",
            is_impulsive=False,
            expense_date=today_str,
            items=[]
        ))
        # Impulse expense: 1500
        await expense_repo.create_expense(ExpenseDB(
            user_id=user.id,
            merchant="Снеки на кассе",
            amount=1500.0,
            category="food",
            is_impulsive=True,
            impulse_reason="Захотелось сладкого",
            expense_date=today_str,
            items=[]
        ))

        res = await client.get("/api/stats/weekly-summary", headers=headers)
        assert res.status_code == 200
        data = res.json()

        assert data["target_calories"] == 2800
        assert data["surplus_days"] >= 1
        assert data["total_expenses"] == 6500.0
        assert data["impulse_expenses_total"] == 1500.0
        assert abs(data["impulse_percentage"] - 23.1) < 0.2
        assert "Воскресная сводка" in data["summary_text"]
        assert "Питание (набор массы)" in data["summary_text"]
        assert "Финансы" in data["summary_text"]
