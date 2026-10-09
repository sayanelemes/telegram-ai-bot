import pytest
from app.services.expenses import ExpenseService
from app.database.models import ExpenseDB


@pytest.mark.asyncio
async def test_expense_service_stats(user_repo, expense_repo):
    user = await user_repo.get_or_create_user(telegram_id=654321, timezone="Asia/Almaty")
    service = ExpenseService(expense_repo)

    from datetime import datetime
    from zoneinfo import ZoneInfo
    today_str = datetime.now(ZoneInfo("Asia/Almaty")).strftime("%Y-%m-%d")

    # Add a couple of expenses
    await expense_repo.create_expense(ExpenseDB(
        user_id=user.id,
        merchant="Magnum",
        amount=4500.0,
        currency="₸",
        category="food",
        expense_date=today_str,
    ))
    await expense_repo.create_expense(ExpenseDB(
        user_id=user.id,
        merchant="Яндекс Такси",
        amount=1500.0,
        currency="₸",
        category="transport",
        expense_date=today_str,
    ))

    # Add an income
    await expense_repo.create_expense(ExpenseDB(
        user_id=user.id,
        merchant="Зарплата",
        amount=500000.0,
        currency="₸",
        category="salary",
        entry_type="income",
        expense_date=today_str,
    ))

    stats = await service.get_expense_statistics(user.id, timezone_str="Asia/Almaty")
    assert stats["today_total"] == 6000.0
    assert stats["week_total"] == 6000.0
    assert stats["month_total"] == 6000.0
    assert stats["month_income"] == 500000.0
    assert stats["net_balance"] == 494000.0
    assert len(stats["categories"]) == 2

    # Check category names
    assert ExpenseService.get_category_name("food") == "🍔 Еда"
    assert ExpenseService.get_category_name("salary") == "💰 Зарплата"
