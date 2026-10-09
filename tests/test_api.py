import hmac
import hashlib
import json
import urllib.parse
import pytest
from httpx import AsyncClient, ASGITransport

from app.api.app import create_app
from app.api.deps import setup_dependencies
from app.api.auth import validate_telegram_init_data
from app.database.models import UserProfileDB, CalorieGoalDB, FoodEntryDB, FoodItemDB, ExpenseDB
from app.services.nutrition import NutritionService
from app.services.expenses import ExpenseService
from app.services.reminders import ReminderService


def make_valid_init_data(bot_token: str, user_id: int, first_name: str = "User") -> str:
    user_json = json.dumps({"id": user_id, "first_name": first_name}, separators=(",", ":"))
    params = {
        "auth_date": "1728400000",
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": user_json,
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    hash_val = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    params["hash"] = hash_val
    return urllib.parse.urlencode(params)


from app.config.settings import settings


@pytest.fixture
def bot_token():
    return settings.BOT_TOKEN


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


# --- 1. Telegram initData validation tests ---

def test_telegram_init_data_validation(bot_token):
    # Valid
    valid_data = make_valid_init_data(bot_token, user_id=111, first_name="ValidUser")
    res = validate_telegram_init_data(valid_data, bot_token)
    assert res is not None
    assert res["id"] == 111
    assert res["first_name"] == "ValidUser"

    # Invalid / tampered hash
    tampered_data = valid_data.replace("ValidUser", "Attacker")
    assert validate_telegram_init_data(tampered_data, bot_token) is None

    # Empty string
    assert validate_telegram_init_data("", bot_token) is None


# --- 2. Dashboard & Remaining / Exceeded Calories tests ---

@pytest.mark.asyncio
async def test_dashboard_remaining_calories(app_instance, user_repo, food_repo, bot_token):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 2001
        auth_header = make_valid_init_data(bot_token, user_id, "UserA")
        headers = {"X-Telegram-Init-Data": auth_header}

        # Create user profile & 2200 kcal goal
        user = await user_repo.get_or_create_user(telegram_id=user_id)
        await user_repo.save_calorie_goal(CalorieGoalDB(
            user_id=user.id,
            bmr=1800,
            tdee=2400,
            target_calories=2200,
            target_protein_g=130,
            target_fat_g=70,
            target_carbs_g=275,
        ))

        from datetime import datetime
        from zoneinfo import ZoneInfo
        today_str = datetime.now(ZoneInfo("Asia/Almaty")).strftime("%Y-%m-%d")

        # Add 1450 kcal consumed food
        await food_repo.create_food_entry(FoodEntryDB(
            user_id=user.id,
            meal_type="Обед",
            entry_date=today_str,
            entry_time="13:00",
            total_calories=1450,
            total_protein=82.0,
            total_fat=48.0,
            total_carbs=170.0,
        ))

        # Request dashboard
        resp = await client.get("/api/dashboard", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        # Section 3 & 20 specific assertion:
        # 2200 goal, 1450 consumed => 750 remaining, 0 exceeded
        assert data["calories"]["goal"] == 2200
        assert data["calories"]["consumed"] == 1450
        assert data["calories"]["remaining"] == 750
        assert data["calories"]["exceeded"] == 0


@pytest.mark.asyncio
async def test_dashboard_exceeded_calories(app_instance, user_repo, food_repo, bot_token):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 2002
        auth_header = make_valid_init_data(bot_token, user_id, "UserExceed")
        headers = {"X-Telegram-Init-Data": auth_header}

        user = await user_repo.get_or_create_user(telegram_id=user_id)
        await user_repo.save_calorie_goal(CalorieGoalDB(
            user_id=user.id,
            bmr=1800,
            tdee=2400,
            target_calories=2200,
            target_protein_g=130,
            target_fat_g=70,
            target_carbs_g=275,
        ))

        from datetime import datetime
        from zoneinfo import ZoneInfo
        today_str = datetime.now(ZoneInfo("Asia/Almaty")).strftime("%Y-%m-%d")

        # Add 2380 kcal consumed food
        await food_repo.create_food_entry(FoodEntryDB(
            user_id=user.id,
            meal_type="Ужин",
            entry_date=today_str,
            entry_time="19:00",
            total_calories=2380,
            total_protein=140.0,
            total_fat=80.0,
            total_carbs=290.0,
        ))

        resp = await client.get("/api/dashboard", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        # Section 3 & 20 specific assertion:
        # 2200 goal, 2380 consumed => 0 remaining, 180 exceeded
        assert data["calories"]["goal"] == 2200
        assert data["calories"]["consumed"] == 2380
        assert data["calories"]["remaining"] == 0
        assert data["calories"]["exceeded"] == 180


# --- 3. Food and Expense API tests ---

@pytest.mark.asyncio
async def test_food_api_analyze_and_save(app_instance, bot_token):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        auth_header = make_valid_init_data(bot_token, 3001, "FoodUser")
        headers = {"X-Telegram-Init-Data": auth_header}

        # 1. Analyze text description
        analyze_resp = await client.post(
            "/api/food/analyze/text",
            headers=headers,
            json={"text": "Овсяная каша"}
        )
        assert analyze_resp.status_code == 200
        analyzed = analyze_resp.json()
        assert analyzed["total_calories"] == 180

        # 2. Confirm and save
        save_resp = await client.post(
            "/api/food",
            headers=headers,
            json={
                "meal_name": analyzed["meal_name"],
                "total_calories": analyzed["total_calories"],
                "total_protein": analyzed["total_protein"],
                "total_fat": analyzed["total_fat"],
                "total_carbs": analyzed["total_carbs"],
                "items": analyzed["items"],
            }
        )
        assert save_resp.status_code == 200
        saved = save_resp.json()
        assert saved["id"] > 0
        assert saved["total_calories"] == 180


@pytest.mark.asyncio
async def test_expense_api_analyze_and_save(app_instance, bot_token):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        auth_header = make_valid_init_data(bot_token, 4001, "ExpenseUser")
        headers = {"X-Telegram-Init-Data": auth_header}

        # Analyze text
        analyze_resp = await client.post(
            "/api/expenses/analyze/text",
            headers=headers,
            json={"text": "кофе 1200 тг"}
        )
        assert analyze_resp.status_code == 200
        analyzed = analyze_resp.json()
        assert analyzed["amount"] == 1200.0

        # Save expense with impulsive flag
        save_resp = await client.post(
            "/api/expenses",
            headers=headers,
            json={
                "merchant": analyzed["merchant"],
                "amount": analyzed["amount"],
                "currency": analyzed["currency"],
                "category": analyzed["category"],
                "entry_type": "expense",
                "is_impulsive": True,
                "ai_analysis": "⚠️ Импульсивная покупка!",
                "items": analyzed["items"],
            }
        )
        assert save_resp.status_code == 200
        saved = save_resp.json()
        assert saved["amount"] == 1200.0
        assert saved["is_impulsive"] is True
        assert saved["entry_type"] == "expense"

        # Test Budget endpoints
        budget_resp = await client.post(
            "/api/expenses/budget",
            headers=headers,
            json={"weekly_budget": 35000.0, "monthly_budget": 150000.0}
        )
        assert budget_resp.status_code == 200
        b_data = budget_resp.json()
        assert b_data["weekly_budget"] == 35000.0
        assert b_data["monthly_budget"] == 150000.0

        # Delete expense
        del_resp = await client.delete(f"/api/expenses/{saved['id']}", headers=headers)
        assert del_resp.status_code == 200
        assert del_resp.json()["success"] is True


@pytest.mark.asyncio
async def test_food_delete_api(app_instance, bot_token):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        auth_header = make_valid_init_data(bot_token, 4002, "FoodUser")
        headers = {"X-Telegram-Init-Data": auth_header}

        # Save food
        save_resp = await client.post(
            "/api/food",
            headers=headers,
            json={
                "meal_name": "Тост с авокадо",
                "total_calories": 250,
                "total_protein": 6.0,
                "total_fat": 12.0,
                "total_carbs": 24.0,
                "items": [{"name": "Авокадо", "portion_g": 50, "calories": 80, "protein_g": 1, "fat_g": 7, "carbs_g": 4}],
            }
        )
        assert save_resp.status_code == 200
        saved = save_resp.json()

        # Delete food
        del_resp = await client.delete(f"/api/food/entries/{saved['id']}", headers=headers)
        assert del_resp.status_code == 200
        assert del_resp.json()["success"] is True


# --- 4. Profile update and automatic target recalculation ---

@pytest.mark.asyncio
async def test_profile_update_recalculates_targets(app_instance, bot_token):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        auth_header = make_valid_init_data(bot_token, 5001, "Sayan")
        headers = {"X-Telegram-Init-Data": auth_header}

        # Update profile: 17yo, 178cm, 49kg, sedentary, gain
        resp = await client.patch(
            "/api/profile",
            headers=headers,
            json={
                "gender": "male",
                "age": 17,
                "height_cm": 178.0,
                "weight_kg": 49.0,
                "activity_level": "sedentary",
                "goal": "gain"
            }
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["age"] == 17
        assert data["weight_kg"] == 49.0
        assert data["target_calories"] > 0
        assert data["bmr"] > 0
        assert data["tdee"] > 0


# --- 5. User isolation: User A cannot delete or access User B's entries ---

@pytest.mark.asyncio
async def test_user_data_isolation(app_instance, user_repo, food_repo, bot_token):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user A and food entry
        user_a = await user_repo.get_or_create_user(telegram_id=6001, first_name="UserA")
        entry_a = await food_repo.create_food_entry(FoodEntryDB(
            user_id=user_a.id,
            meal_type="Завтрак",
            entry_date="2026-10-08",
            entry_time="09:00",
            total_calories=300,
            total_protein=10.0,
            total_fat=5.0,
            total_carbs=40.0,
        ))

        # User B attempts to delete User A's meal
        auth_b = make_valid_init_data(bot_token, 6002, "UserB")
        headers_b = {"X-Telegram-Init-Data": auth_b}

        del_resp = await client.delete(f"/api/food/{entry_a.id}", headers=headers_b)
        # Must return 404 because entry does not belong to User B
        assert del_resp.status_code == 404

        # Verify entry still exists
        remaining = await food_repo.get_entry_by_id(entry_a.id)
        assert remaining is not None


@pytest.mark.asyncio
async def test_standalone_auth_and_code(app_instance, user_repo):
    from app.api.auth import create_login_code, create_auth_token

    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Generate login code for telegram_id 7777
        code = create_login_code(7777)

        # 2. Verify code endpoint
        verify_resp = await client.post("/api/auth/code", json={"code": code})
        assert verify_resp.status_code == 200
        data = verify_resp.json()
        assert data["success"] is True
        token = data["token"]
        assert token is not None

        # 3. Use returned token to access protected endpoint /api/me
        me_resp = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert me_data["telegram_id"] == 7777

        # 4. In-Telegram user can fetch their standalone token from /api/auth/token
        token_resp = await client.get("/api/auth/token", headers={"Authorization": f"Bearer {token}"})
        assert token_resp.status_code == 200
        assert "token" in token_resp.json()

