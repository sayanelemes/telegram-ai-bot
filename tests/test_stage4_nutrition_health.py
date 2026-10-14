import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.database.models import UserProfileDB, CalorieGoalDB, FoodEntryDB, FoodItemDB
from tests.test_api import make_valid_init_data


@pytest.mark.asyncio
async def test_portion_editing_with_macro_recalculation(app_instance, user_repo, food_repo, test_settings):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 9101
        auth_header = make_valid_init_data(test_settings.BOT_TOKEN, user_id, "UserPortion")
        headers = {"X-Telegram-Init-Data": auth_header}

        user = await user_repo.get_or_create_user(telegram_id=user_id)

        # Create food entry: Rice 100g (130 kcal, 2.5g P, 0.5g F, 28g C)
        entry = await food_repo.create_food_entry(FoodEntryDB(
            user_id=user.id,
            meal_type="Обед",
            entry_date="2026-10-14",
            entry_time="13:00",
            total_calories=130,
            total_protein=2.5,
            total_fat=0.5,
            total_carbs=28.0,
            items=[
                FoodItemDB(
                    name="Рис",
                    portion_g=100.0,
                    calories=130,
                    protein_g=2.5,
                    fat_g=0.5,
                    carbs_g=28.0
                )
            ]
        ))

        item_id = entry.items[0].id

        # Update portion: +50g (to 150g -> 1.5x)
        resp = await client.patch(
            f"/api/food/entries/{entry.id}/items/{item_id}",
            headers=headers,
            json={"delta_g": 50.0}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"][0]["portion_g"] == 150.0
        assert data["items"][0]["calories"] == 195  # 130 * 1.5
        assert data["total_calories"] == 195


@pytest.mark.asyncio
async def test_repeat_yesterday_meals(app_instance, user_repo, food_repo, test_settings):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 9102
        auth_header = make_valid_init_data(test_settings.BOT_TOKEN, user_id, "UserRepeat")
        headers = {"X-Telegram-Init-Data": auth_header}

        user = await user_repo.get_or_create_user(telegram_id=user_id)
        tz = ZoneInfo("Asia/Almaty")
        yesterday_str = (datetime.now(tz) - timedelta(days=1)).strftime("%Y-%m-%d")

        # Create meal yesterday
        await food_repo.create_food_entry(FoodEntryDB(
            user_id=user.id,
            meal_type="Завтрак",
            entry_date=yesterday_str,
            entry_time="09:00",
            total_calories=450,
            total_protein=30.0,
            total_fat=15.0,
            total_carbs=45.0,
            items=[FoodItemDB(name="Омлет", portion_g=200, calories=450, protein_g=30, fat_g=15, carbs_g=45)]
        ))

        # Repeat yesterday
        repeat_resp = await client.post("/api/food/repeat-yesterday", headers=headers)
        assert repeat_resp.status_code == 200
        created = repeat_resp.json()
        assert len(created) == 1
        assert created[0]["total_calories"] == 450


@pytest.mark.asyncio
async def test_custom_foods_priority(app_instance, user_repo, test_settings):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 9103
        auth_header = make_valid_init_data(test_settings.BOT_TOKEN, user_id, "UserCustom")
        headers = {"X-Telegram-Init-Data": auth_header}

        # 1. Create custom food
        c_resp = await client.post(
            "/api/food/custom",
            headers=headers,
            json={
                "name": "Мой протеиновый коктейль",
                "calories_per_100g": 380,
                "protein_per_100g": 45.0,
                "fat_per_100g": 6.0,
                "carbs_per_100g": 36.0,
                "is_favorite": True
            }
        )
        assert c_resp.status_code == 200

        # 2. Analyze text matching this custom food
        analyze_resp = await client.post(
            "/api/food/analyze/text",
            headers=headers,
            json={"text": "Мой протеиновый коктейль"}
        )
        assert analyze_resp.status_code == 200
        data = analyze_resp.json()
        assert data["total_calories"] == 380
        assert data["total_protein"] == 45.0


@pytest.mark.asyncio
async def test_weight_tracking_and_auto_recalculation(app_instance, user_repo, test_settings):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 9104
        auth_header = make_valid_init_data(test_settings.BOT_TOKEN, user_id, "UserWeight")
        headers = {"X-Telegram-Init-Data": auth_header}

        user = await user_repo.get_or_create_user(telegram_id=user_id)

        # Initial profile: 70 kg
        await user_repo.save_profile(UserProfileDB(
            user_id=user.id,
            gender="male",
            age=25,
            height_cm=180.0,
            weight_kg=70.0,
            activity_level="moderate",
            goal="gain"
        ))
        await user_repo.save_calorie_goal(CalorieGoalDB(
            user_id=user.id,
            bmr=1700,
            tdee=2600,
            target_calories=2900,
            target_protein_g=140,
            target_fat_g=80,
            target_carbs_g=400
        ))

        # Log small weight shift (+0.5 kg -> 70.5) -> should NOT recalculate
        w_small = await client.post("/api/health/weight", headers=headers, json={"weight_kg": 70.5})
        assert w_small.status_code == 200
        assert w_small.json()["recalculated"] is False

        # Log major weight shift (73.0 kg -> delta 3.0 kg >= 2.0 kg) -> MUST recalculate!
        w_big = await client.post("/api/health/weight", headers=headers, json={"weight_kg": 73.0})
        assert w_big.status_code == 200
        res_data = w_big.json()
        assert res_data["recalculated"] is True
        assert res_data["targets"] is not None
        assert res_data["targets"]["target_calories"] > 0


@pytest.mark.asyncio
async def test_water_tracking(app_instance, test_settings):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 9105
        auth_header = make_valid_init_data(test_settings.BOT_TOKEN, user_id, "UserWater")
        headers = {"X-Telegram-Init-Data": auth_header}

        resp = await client.post("/api/health/water", headers=headers, json={"amount_ml": 250})
        assert resp.status_code == 200
        assert resp.json()["today_total_ml"] == 250

        resp2 = await client.post("/api/health/water", headers=headers, json={"amount_ml": 500})
        assert resp2.status_code == 200
        assert resp2.json()["today_total_ml"] == 750


@pytest.mark.asyncio
async def test_pantry_and_auto_writeoff(app_instance, user_repo, food_repo, test_settings):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 9106
        auth_header = make_valid_init_data(test_settings.BOT_TOKEN, user_id, "UserPantry")
        headers = {"X-Telegram-Init-Data": auth_header}

        # 1. Add pantry item "Овсянка"
        add_p = await client.post("/api/pantry", headers=headers, json={"name": "Овсянка"})
        assert add_p.status_code == 200

        # Check in pantry
        p_list = await client.get("/api/pantry", headers=headers)
        assert len(p_list.json()) == 1
        assert p_list.json()[0]["name"] == "Овсянка"

        # 2. Log food "Овсянка с молоком" -> triggers pantry deduction
        save_food = await client.post(
            "/api/food",
            headers=headers,
            json={
                "meal_type": "Завтрак",
                "total_calories": 250,
                "total_protein": 8.0,
                "total_fat": 5.0,
                "total_carbs": 40.0,
                "items": [{"name": "Овсянка", "portion_g": 60, "calories": 250, "protein_g": 8, "fat_g": 5, "carbs_g": 40}]
            }
        )
        assert save_food.status_code == 200

        # 3. Check pantry: "Овсянка" should be deducted
        p_after = await client.get("/api/pantry", headers=headers)
        assert len(p_after.json()) == 0
