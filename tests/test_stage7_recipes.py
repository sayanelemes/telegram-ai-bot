import pytest
import hmac
import hashlib
import json
from unittest.mock import AsyncMock
from urllib.parse import urlencode
from datetime import datetime
from zoneinfo import ZoneInfo
from httpx import AsyncClient, ASGITransport

from app.database.models import CalorieGoalDB
from app.services.gemini import (
    RecipeGenerated,
    RecipeIngredient,
    WeeklyMealPlanResult,
    DayPlan,
    MealPlanItem,
    ShoppingAisleGroup,
)


def make_valid_init_data(bot_token: str, user_id: int = 9401, first_name: str = "RecipeUser") -> str:
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


@pytest.fixture
def mock_mocked_recipe():
    return RecipeGenerated(
        name="Творожно-банановый гейнер-шейк",
        description="Мощный белковый шейк для набора массы за 5 минут без варки",
        cooking_time_minutes=5,
        utensils=["Блендер"],
        calories=650,
        protein_g=42.0,
        fat_g=18.0,
        carbs_g=80.0,
        estimated_cost=850.0,
        ingredients=[
            RecipeIngredient(name="Творог 5%", amount="1 пачка (200 г)", grams=200.0, estimated_price=300.0),
            RecipeIngredient(name="Банан", amount="1 шт (120 г)", grams=120.0, estimated_price=150.0),
            RecipeIngredient(name="Овсяные хлопья", amount="4 ст. л. (50 г)", grams=50.0, estimated_price=100.0),
            RecipeIngredient(name="Молоко 3.2%", amount="1.5 стакана (300 мл)", grams=300.0, estimated_price=150.0),
            RecipeIngredient(name="Арахисовая паста", amount="1 ст. л. (30 г)", grams=30.0, estimated_price=150.0),
        ],
        instructions=[
            "Засыпьте овсяные хлопья в блендер и измельчите 30 секунд.",
            "Добавьте творог, банан, арахисовую пасту и залейте молоком.",
            "Взбейте до однородной массы в течение 1 минуты.",
        ],
        high_calorie_bulking_tip="Добавьте столовую ложку мёда для +65 ккал углеводов!"
    )


@pytest.fixture
def mock_mocked_weekly_plan():
    return WeeklyMealPlanResult(
        days=[
            DayPlan(
                day_name="Понедельник",
                meals=[
                    MealPlanItem(meal_type="breakfast", name="Овсянка с яйцами", calories=700, protein_g=35, fat_g=20, carbs_g=85, quick_recipe="Сварить овсянку, пожарить 3 яйца"),
                    MealPlanItem(meal_type="lunch", name="Гречка с куриным филе", calories=800, protein_g=55, fat_g=18, carbs_g=95, quick_recipe="Гречка + филе на сковороде 10 мин"),
                    MealPlanItem(meal_type="dinner", name="Творог с мёдом и орехами", calories=600, protein_g=40, fat_g=22, carbs_g=55, quick_recipe="Смешать творог, мёд, грецкие орехи"),
                    MealPlanItem(meal_type="snack_1", name="Шейк с арахисовой пастой", calories=650, protein_g=30, fat_g=20, carbs_g=80, quick_recipe="Взбить молоко, банан, пасту"),
                ],
                total_calories=2750,
                total_protein=160.0,
                total_fat=80.0,
                total_carbs=315.0
            )
        ],
        weekly_shopping_list=[
            ShoppingAisleGroup(aisle_name="Мясной отдел", items=["Куриное филе 2 кг", "Яйца 3 десятка"]),
            ShoppingAisleGroup(aisle_name="Молочный отдел", items=["Творог 5% 5 пачек", "Молоко 3.2% 4 литра"]),
            ShoppingAisleGroup(aisle_name="Бакалея", items=["Овсяные хлопья 1 кг", "Гречка 1 кг", "Арахисовая паста 1 банка"]),
        ],
        bulking_tips="Пейте калории между приемами пищи в виде шейков, чтобы не перегружать ЖКТ."
    )


@pytest.mark.asyncio
async def test_recipe_suggest_and_caching(app_instance, user_repo, mock_gemini_service, test_settings, mock_mocked_recipe):
    mock_gemini_service.generate_recipe = AsyncMock(return_value=mock_mocked_recipe)

    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 9401
        auth_header = make_valid_init_data(test_settings.BOT_TOKEN, user_id, "RecipeTester")
        headers = {"X-Telegram-Init-Data": auth_header}

        user = await user_repo.get_or_create_user(telegram_id=user_id)
        await user_repo.save_calorie_goal(CalorieGoalDB(
            user_id=user.id,
            bmr=1700,
            tdee=2500,
            target_calories=2900,
            target_protein_g=150,
            target_fat_g=80,
            target_carbs_g=380
        ))

        # Suggest recipe in mode="remaining"
        res = await client.post(
            "/api/recipes/suggest",
            headers=headers,
            json={"mode": "remaining"}
        )
        assert res.status_code == 200
        data = res.json()

        assert data["name"] == "Творожно-банановый гейнер-шейк"
        assert data["calories"] == 650
        assert data["cooking_time_minutes"] <= 15
        assert len(data["utensils"]) <= 2
        assert len(data["ingredients"]) >= 3
        assert data["estimated_cost"] <= 1500.0
        assert "link_id" in data

        # Test GET /api/recipes/last within 24h
        res_last = await client.get("/api/recipes/last", headers=headers)
        assert res_last.status_code == 200
        assert res_last.json()["name"] == data["name"]


@pytest.mark.asyncio
async def test_quick_log_with_idempotency_double_tap(app_instance, user_repo, food_repo, test_settings, mock_mocked_recipe):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 9402
        auth_header = make_valid_init_data(test_settings.BOT_TOKEN, user_id, "QuickLogTester")
        headers = {"X-Telegram-Init-Data": auth_header}

        user = await user_repo.get_or_create_user(telegram_id=user_id)
        # Add item to pantry to verify auto-writeoff
        await food_repo.add_pantry_item(user_id=user.id, name="Творог 5%", amount_str="200 г")

        req_id = "tap_request_unique_12345"
        payload = {
            "request_id": req_id,
            "recipe_data": mock_mocked_recipe.model_dump(),
            "meal_type": "snack"
        }

        # First tap
        res1 = await client.post("/api/meals/quick-log", headers=headers, json=payload)
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["success"] is True
        assert data1["calories"] == 650
        assert "Творог 5%" in data1["deducted_from_pantry"]

        # Check pantry: Творог 5% was written off!
        pantry = await food_repo.get_pantry_items(user.id)
        assert len(pantry) == 0

        # Second tap with IDENTICAL request_id (double-tap attack/glitch)
        res2 = await client.post("/api/meals/quick-log", headers=headers, json=payload)
        assert res2.status_code == 200
        data2 = res2.json()
        # Must return idempotent identical response
        assert data2["entry_id"] == data1["entry_id"]

        # Verify in database: ONLY ONE entry was recorded, NOT two!
        today_str = datetime.now(ZoneInfo(user.timezone)).strftime("%Y-%m-%d")
        entries = await food_repo.get_entries_by_date(user.id, today_str)
        assert len(entries) == 1


@pytest.mark.asyncio
async def test_recipe_to_expense(app_instance, user_repo, expense_repo, test_settings, mock_mocked_recipe):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 9403
        auth_header = make_valid_init_data(test_settings.BOT_TOKEN, user_id, "RecipeExpenseTester")
        headers = {"X-Telegram-Init-Data": auth_header}

        await user_repo.get_or_create_user(telegram_id=user_id)

        res = await client.post(
            "/api/recipes/to-expense",
            headers=headers,
            json={"recipe_data": mock_mocked_recipe.model_dump(), "custom_cost": 850.0}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["amount"] == 850.0

        # Verify expense in DB
        exp = await expense_repo.get_expense_by_id(data["expense_id"])
        assert exp is not None
        assert exp.source == "recipe"
        assert exp.amount == 850.0
        assert "Творожно-банановый" in exp.merchant


@pytest.mark.asyncio
async def test_shopping_list_checklist_and_recipe_export(app_instance, user_repo, test_settings, mock_mocked_recipe):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 9404
        auth_header = make_valid_init_data(test_settings.BOT_TOKEN, user_id, "ShoppingTester")
        headers = {"X-Telegram-Init-Data": auth_header}

        await user_repo.get_or_create_user(telegram_id=user_id)

        # 1. Add manual item
        res_add = await client.post(
            "/api/shopping-list",
            headers=headers,
            json={"name": "Арахисовая паста", "amount_str": "1 банка", "category": "food"}
        )
        assert res_add.status_code == 200
        item_id = res_add.json()["id"]

        # 2. Add all ingredients from recipe in 1 tap
        res_from_rec = await client.post(
            "/api/shopping-list/from-recipe",
            headers=headers,
            json={"recipe_data": mock_mocked_recipe.model_dump()}
        )
        assert res_from_rec.status_code == 200
        assert res_from_rec.json()["count"] == 5

        # 3. List items
        res_list = await client.get("/api/shopping-list", headers=headers)
        assert res_list.status_code == 200
        items = res_list.json()
        assert len(items) == 6

        # 4. Check/toggle item as bought
        res_toggle = await client.patch(
            f"/api/shopping-list/{item_id}",
            headers=headers,
            json={"is_bought": True, "bought_price": 1200.0}
        )
        assert res_toggle.status_code == 200
        assert res_toggle.json()["is_bought"] is True
        assert res_toggle.json()["bought_price"] == 1200.0

        # 5. Clear bought items
        res_clear = await client.delete("/api/shopping-list/cleared", headers=headers)
        assert res_clear.status_code == 200
        assert res_clear.json()["cleared_count"] == 1

        res_remaining = await client.get("/api/shopping-list", headers=headers)
        assert len(res_remaining.json()) == 5


@pytest.mark.asyncio
async def test_weekly_meal_plan_and_import(app_instance, user_repo, mock_gemini_service, test_settings, mock_mocked_weekly_plan):
    mock_gemini_service.generate_weekly_plan = AsyncMock(return_value=mock_mocked_weekly_plan)

    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 9405
        auth_header = make_valid_init_data(test_settings.BOT_TOKEN, user_id, "WeeklyPlanTester")
        headers = {"X-Telegram-Init-Data": auth_header}

        await user_repo.get_or_create_user(telegram_id=user_id)

        # 1. Generate weekly meal plan
        res_plan = await client.post("/api/recipes/weekly-plan", headers=headers, json={"preferences": "Больше белка"})
        assert res_plan.status_code == 200
        data = res_plan.json()
        assert len(data["days"]) >= 1
        assert len(data["weekly_shopping_list"]) >= 1

        # 2. GET stored plan
        res_get = await client.get("/api/recipes/weekly-plan", headers=headers)
        assert res_get.status_code == 200
        assert res_get.json()["bulking_tips"] == data["bulking_tips"]

        # 3. Import weekly shopping list into user's shopping checklist
        res_import = await client.post("/api/shopping-list/import-weekly-plan", headers=headers)
        assert res_import.status_code == 200
        assert res_import.json()["imported_count"] == 7

        # 4. Check shopping list
        res_shop = await client.get("/api/shopping-list", headers=headers)
        assert res_shop.status_code == 200
        assert len(res_shop.json()) == 7
