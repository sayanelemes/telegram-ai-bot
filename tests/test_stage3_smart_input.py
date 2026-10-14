import pytest
from unittest.mock import AsyncMock
from app.services.smart_input import SmartInputService, SmartInputResult, SmartInputItem
from app.services.gemini import GeminiServiceError


@pytest.fixture
def mock_gemini():
    gemini = AsyncMock()
    return gemini


@pytest.mark.asyncio
async def test_fast_paths(temp_db_manager, user_repo):
    user = await user_repo.get_or_create_user(telegram_id=8801)
    service = SmartInputService(db_manager=temp_db_manager, gemini_service=AsyncMock())

    # Water fast-path
    res_water = await service.execute_input("+250", user_id=user.id)
    assert res_water.action == "fast_path"
    assert res_water.water_ml == 250

    # Weight fast-path
    res_weight = await service.execute_input("вес 78.4", user_id=user.id)
    assert res_weight.action == "fast_path"
    assert res_weight.weight_kg == 78.4

    # Verify weight was saved to weight_logs
    async with temp_db_manager.get_connection() as conn:
        cur = await conn.execute("SELECT weight_kg FROM weight_logs WHERE user_id = ?;", (user.id,))
        row = await cur.fetchone()
        assert row["weight_kg"] == 78.4


def test_normalize_price_tokens():
    # 1.5к -> 1500, 12к -> 12000
    assert "1500" in SmartInputService.normalize_price_tokens("купил наушники за 1.5к")
    assert "12000" in SmartInputService.normalize_price_tokens("наушники 12к")
    assert "50000" in SmartInputService.normalize_price_tokens("куртка 50k")


@pytest.mark.asyncio
async def test_snickers_food_and_expense(temp_db_manager, user_repo, mock_gemini):
    user = await user_repo.get_or_create_user(telegram_id=8802)
    service = SmartInputService(db_manager=temp_db_manager, gemini_service=mock_gemini)

    # Mock Gemini structured response for "купил сникерс за 400 тенге"
    service.parse_single_phrase = AsyncMock(return_value=SmartInputResult(
        intent="food_and_expense",
        confidence=0.95,
        currency="₸",
        items=[
            SmartInputItem(
                name="Сникерс",
                grams=50.0,
                calories=250,
                protein_g=4.0,
                fat_g=12.0,
                carbs_g=30.0,
                price=400.0,
                category="food",
                is_impulse=True,
                impulse_reason="Сладости и снеки"
            )
        ]
    ))

    outcome = await service.execute_input("купил сникерс за 400 тенге", user_id=user.id)
    assert outcome.action == "saved"
    assert outcome.link_id is not None
    assert outcome.food_entry_id is not None
    assert outcome.expense_id is not None
    assert "250 ккал" in outcome.message
    assert "400" in outcome.message
    assert "импульсивная" in outcome.message

    # Verify both food and expense share the exact same link_id in database
    async with temp_db_manager.get_connection() as conn:
        f_cur = await conn.execute("SELECT link_id, total_calories FROM food_entries WHERE id = ?;", (outcome.food_entry_id,))
        f_row = await f_cur.fetchone()
        assert f_row["link_id"] == outcome.link_id
        assert f_row["total_calories"] == 250

        e_cur = await conn.execute("SELECT link_id, amount, is_impulsive FROM expenses WHERE id = ?;", (outcome.expense_id,))
        e_row = await e_cur.fetchone()
        assert e_row["link_id"] == outcome.link_id
        assert e_row["amount"] == 400.0
        assert e_row["is_impulsive"] == 1

    # Test joint undo
    undo_success = await service.undo_by_link_id(outcome.link_id, user_id=user.id)
    assert undo_success is True

    # Both must be deleted
    async with temp_db_manager.get_connection() as conn:
        f_check = await conn.execute("SELECT COUNT(*) FROM food_entries WHERE link_id = ?;", (outcome.link_id,))
        assert (await f_check.fetchone())[0] == 0
        e_check = await conn.execute("SELECT COUNT(*) FROM expenses WHERE link_id = ?;", (outcome.link_id,))
        assert (await e_check.fetchone())[0] == 0


@pytest.mark.asyncio
async def test_food_only_no_expense(temp_db_manager, user_repo, mock_gemini):
    user = await user_repo.get_or_create_user(telegram_id=8803)
    service = SmartInputService(db_manager=temp_db_manager, gemini_service=mock_gemini)

    service.parse_single_phrase = AsyncMock(return_value=SmartInputResult(
        intent="food_only",
        confidence=0.9,
        currency="₸",
        items=[
            SmartInputItem(name="Яйца варёные (2 шт)", grams=110.0, calories=150, protein_g=13.0, fat_g=10.0, carbs_g=1.0, price=None),
            SmartInputItem(name="Бутерброд", grams=100.0, calories=220, protein_g=6.0, fat_g=8.0, carbs_g=28.0, price=None),
        ]
    ))

    outcome = await service.execute_input("съел два яйца и бутерброд", user_id=user.id)
    assert outcome.action == "saved"
    assert outcome.food_entry_id is not None
    assert outcome.expense_id is None

    # Verify no expenses created
    async with temp_db_manager.get_connection() as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM expenses WHERE user_id = ?;", (user.id,))
        assert (await cur.fetchone())[0] == 0


@pytest.mark.asyncio
async def test_expense_only_no_calories(temp_db_manager, user_repo, mock_gemini):
    user = await user_repo.get_or_create_user(telegram_id=8804)
    service = SmartInputService(db_manager=temp_db_manager, gemini_service=mock_gemini)

    # "такси 2500"
    service.parse_single_phrase = AsyncMock(return_value=SmartInputResult(
        intent="expense_only",
        confidence=0.95,
        currency="₸",
        items=[
            SmartInputItem(name="Такси", price=2500.0, category="transport", is_impulse=False)
        ]
    ))

    outcome = await service.execute_input("такси 2500", user_id=user.id)
    assert outcome.action == "saved"
    assert outcome.expense_id is not None
    assert outcome.food_entry_id is None

    # Verify no food created
    async with temp_db_manager.get_connection() as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM food_entries WHERE user_id = ?;", (user.id,))
        assert (await cur.fetchone())[0] == 0


@pytest.mark.asyncio
async def test_multiple_items_with_prices(temp_db_manager, user_repo, mock_gemini):
    user = await user_repo.get_or_create_user(telegram_id=8805)
    service = SmartInputService(db_manager=temp_db_manager, gemini_service=mock_gemini)

    # "кофе 1200 и сэндвич 2500"
    service.parse_single_phrase = AsyncMock(return_value=SmartInputResult(
        intent="food_and_expense",
        confidence=0.95,
        currency="₸",
        items=[
            SmartInputItem(name="Кофе", calories=80, protein_g=2.0, fat_g=3.0, carbs_g=10.0, price=1200.0, is_impulse=True),
            SmartInputItem(name="Сэндвич", calories=380, protein_g=18.0, fat_g=14.0, carbs_g=42.0, price=2500.0, is_impulse=False),
        ]
    ))

    outcome = await service.execute_input("кофе 1200 и сэндвич 2500", user_id=user.id)
    assert outcome.action == "saved"
    assert outcome.food_entry_id is not None
    assert outcome.expense_id is not None

    async with temp_db_manager.get_connection() as conn:
        f_cur = await conn.execute("SELECT total_calories FROM food_entries WHERE id = ?;", (outcome.food_entry_id,))
        assert (await f_cur.fetchone())["total_calories"] == 460

        e_cur = await conn.execute("SELECT amount FROM expenses WHERE id = ?;", (outcome.expense_id,))
        assert (await e_cur.fetchone())["amount"] == 3700.0


@pytest.mark.asyncio
async def test_greeting_ignored(temp_db_manager, user_repo, mock_gemini):
    user = await user_repo.get_or_create_user(telegram_id=8806)
    service = SmartInputService(db_manager=temp_db_manager, gemini_service=mock_gemini)

    service.parse_single_phrase = AsyncMock(return_value=SmartInputResult(
        intent="other",
        confidence=0.99,
        items=[]
    ))

    outcome = await service.execute_input("привет", user_id=user.id)
    assert outcome.action == "ignored"

    # Verify database is untouched
    async with temp_db_manager.get_connection() as conn:
        f_cur = await conn.execute("SELECT COUNT(*) FROM food_entries WHERE user_id = ?;", (user.id,))
        assert (await f_cur.fetchone())[0] == 0


@pytest.mark.asyncio
async def test_gemini_failure_writes_nothing(temp_db_manager, user_repo, mock_gemini):
    user = await user_repo.get_or_create_user(telegram_id=8807)
    service = SmartInputService(db_manager=temp_db_manager, gemini_service=mock_gemini)

    # Gemini throws error
    service.parse_single_phrase = AsyncMock(side_effect=GeminiServiceError("AI unavailable"))

    with pytest.raises(GeminiServiceError):
        await service.execute_input("съел пиццу за 3000", user_id=user.id)

    # Database must have 0 records
    async with temp_db_manager.get_connection() as conn:
        f_cur = await conn.execute("SELECT COUNT(*) FROM food_entries WHERE user_id = ?;", (user.id,))
        assert (await f_cur.fetchone())[0] == 0
        e_cur = await conn.execute("SELECT COUNT(*) FROM expenses WHERE user_id = ?;", (user.id,))
        assert (await e_cur.fetchone())[0] == 0
