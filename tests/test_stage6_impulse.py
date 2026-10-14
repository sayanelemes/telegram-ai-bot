import pytest
import hmac
import hashlib
import json
from urllib.parse import urlencode
from datetime import datetime
from zoneinfo import ZoneInfo
from httpx import AsyncClient, ASGITransport

from app.database.models import ExpenseDB


def make_valid_init_data(bot_token: str, user_id: int = 9301, first_name: str = "ImpulseUser") -> str:
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
async def test_patch_expense_impulse_toggle_and_reason(app_instance, user_repo, expense_repo, test_settings):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 9301
        auth_header = make_valid_init_data(test_settings.BOT_TOKEN, user_id, "ImpulseTester")
        headers = {"X-Telegram-Init-Data": auth_header}

        user = await user_repo.get_or_create_user(telegram_id=user_id)
        today_str = datetime.now(ZoneInfo(user.timezone)).strftime("%Y-%m-%d")

        # Create normal expense
        exp = await expense_repo.create_expense(ExpenseDB(
            user_id=user.id,
            merchant="Coffee Shop",
            amount=1500.0,
            category="food",
            is_impulsive=False,
            expense_date=today_str,
            items=[]
        ))

        # 1. Toggle via PATCH (without body -> flips to True)
        res1 = await client.patch(f"/api/expenses/{exp.id}/impulse", headers=headers)
        assert res1.status_code == 200
        assert res1.json()["is_impulsive"] is True

        # Verify in DB
        db_exp = await expense_repo.get_expense_by_id(exp.id)
        assert db_exp.is_impulse is True
        assert db_exp.is_impulsive is True

        # 2. Update with explicit reason
        res2 = await client.patch(
            f"/api/expenses/{exp.id}/impulse",
            headers=headers,
            json={"is_impulse": True, "impulse_reason": "Кофе навынос на прогулке"}
        )
        assert res2.status_code == 200
        assert res2.json()["is_impulsive"] is True

        db_exp2 = await expense_repo.get_expense_by_id(exp.id)
        assert db_exp2.impulse_reason == "Кофе навынос на прогулке"

        # 3. Toggle back to False
        res3 = await client.patch(
            f"/api/expenses/{exp.id}/impulse",
            headers=headers,
            json={"is_impulse": False}
        )
        assert res3.status_code == 200
        assert res3.json()["is_impulsive"] is False

        # 4. Enforce user isolation: user 9302 cannot toggle user 9301's expense
        auth_other = make_valid_init_data(test_settings.BOT_TOKEN, 9302, "OtherUser")
        res_other = await client.patch(
            f"/api/expenses/{exp.id}/impulse",
            headers={"X-Telegram-Init-Data": auth_other}
        )
        assert res_other.status_code == 404


@pytest.mark.asyncio
async def test_impulse_stats_and_protein_food_equivalents(app_instance, user_repo, expense_repo, test_settings):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = 9303
        auth_header = make_valid_init_data(test_settings.BOT_TOKEN, user_id, "ProteinEqUser")
        headers = {"X-Telegram-Init-Data": auth_header}

        user = await user_repo.get_or_create_user(telegram_id=user_id)
        today_str = datetime.now(ZoneInfo(user.timezone)).strftime("%Y-%m-%d")

        # Set monthly impulse limit: 5 000 KZT
        await client.post(
            "/api/expenses/impulse-limit",
            headers=headers,
            json={"impulse_monthly_limit": 5000.0}
        )

        # Normal food expense: 15 000 KZT
        await expense_repo.create_expense(ExpenseDB(
            user_id=user.id,
            merchant="Magnum Supermarket",
            amount=15000.0,
            category="food",
            is_impulsive=False,
            expense_date=today_str,
            items=[]
        ))

        # Impulse expense 1: 3 000 KZT (Snacks)
        await expense_repo.create_expense(ExpenseDB(
            user_id=user.id,
            merchant="Fast Food",
            amount=3000.0,
            category="food",
            is_impulsive=True,
            impulse_reason="Фастфуд после работы",
            expense_date=today_str,
            items=[]
        ))

        # Impulse expense 2: 4 000 KZT (Impulse shopping)
        await expense_repo.create_expense(ExpenseDB(
            user_id=user.id,
            merchant="Souvenirs",
            amount=4000.0,
            category="shopping",
            is_impulsive=True,
            impulse_reason="Эмоциональная покупка",
            expense_date=today_str,
            items=[]
        ))

        # Total spent: 22 000 KZT
        # Total impulse: 7 000 KZT (> limit 5 000 KZT -> EXCEEDED!)
        res = await client.get("/api/expenses/impulse-stats", headers=headers)
        assert res.status_code == 200
        data = res.json()

        assert data["total_spent"] == 22000.0
        assert data["impulse_total"] == 7000.0
        assert data["impulse_count"] == 2
        assert abs(data["impulse_percentage"] - 31.8) < 0.2
        assert data["is_limit_exceeded"] is True
        assert data["food_days_cost"] > 0

        # Check protein equivalents for 7 000 KZT:
        # Chicken (~2200/kg): 7000 / 2200 = 3.2 kg
        # Cottage cheese (~600/pack): 7000 / 600 = 11.7 packs
        # Eggs (~700/dozen): 7000 / 700 = 10.0 dozens
        eq = data["protein_equivalents"]
        assert eq["chicken_kg"] == 3.2
        assert eq["cottage_cheese_packs"] == 11.7
        assert eq["eggs_dozens"] == 10.0

        # Warning message is generated with details
        warn = data["warning_message"]
        assert warn is not None
        assert "Превышен лимит на импульсивные покупки" in warn
        assert "куриного филе" in warn
        assert "пачек творога" in warn


@pytest.mark.asyncio
async def test_bot_link_id_impulse_toggle(app_instance, user_repo, expense_repo):
    user_id = 9304
    user = await user_repo.get_or_create_user(telegram_id=user_id)
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    await expense_repo.create_expense(ExpenseDB(
        user_id=user.id,
        merchant="Snack Bar",
        amount=800.0,
        category="food",
        link_id="test_link_123",
        is_impulsive=False,
        expense_date=today_str,
        items=[]
    ))

    # Toggle by link_id
    toggled = await expense_repo.toggle_impulse_by_link_id(user_id=user.id, link_id="test_link_123")
    assert toggled is not None
    assert toggled.is_impulse is True
    assert toggled.is_impulsive is True

    # Toggle again -> False
    toggled2 = await expense_repo.toggle_impulse_by_link_id(user_id=user.id, link_id="test_link_123")
    assert toggled2 is not None
    assert toggled2.is_impulse is False
    assert toggled2.is_impulsive is False
