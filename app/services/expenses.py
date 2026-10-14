from datetime import datetime, timedelta
from typing import Dict, Any
from zoneinfo import ZoneInfo
from app.database.repositories.expense_repository import ExpenseRepository


class ExpenseService:
    CATEGORY_LABELS = {
        "food": "🍔 Еда",
        "transport": "🚕 Транспорт",
        "shopping": "🛒 Покупки",
        "entertainment": "🎟 Развлечения",
        "utilities": "💡 Счета и услуги",
        "salary": "💰 Зарплата",
        "business": "💼 Бизнес / Фриланс",
        "gift": "🎁 Подарок",
        "investments": "📈 Инвестиции",
        "other_income": "💵 Другой доход",
        "other": "📦 Другое",
    }

    def __init__(self, expense_repo: ExpenseRepository):
        self.expense_repo = expense_repo

    @classmethod
    def get_category_name(cls, category: str) -> str:
        return cls.CATEGORY_LABELS.get(category.lower(), f"📦 {category.capitalize()}")

    async def get_expense_statistics(
        self,
        user_id: int,
        timezone_str: str = "Asia/Almaty"
    ) -> Dict[str, Any]:
        """
        Calculate expenses & income for today, current week (last 7 days), and current calendar month.
        """
        tz = ZoneInfo(timezone_str)
        now = datetime.now(tz)

        today_str = now.strftime("%Y-%m-%d")
        seven_days_ago_str = (now - timedelta(days=6)).strftime("%Y-%m-%d")
        month_start_str = now.strftime("%Y-%m-01")
        month_name = now.strftime("%B")

        month_names_ru = {
            1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
            5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
            9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
        }
        current_month_title = month_names_ru.get(now.month, month_name)

        today_total = await self.expense_repo.get_daily_total(user_id, today_str)
        week_total = await self.expense_repo.get_period_total(user_id, seven_days_ago_str, today_str)
        month_total = await self.expense_repo.get_period_total(user_id, month_start_str, today_str)

        # Incomes
        month_income = await self.expense_repo.get_income_period_total(user_id, month_start_str, today_str)
        net_balance = month_income - month_total

        categories_month = await self.expense_repo.get_period_categories(
            user_id, month_start_str, today_str
        )

        formatted_categories = []
        for cat in categories_month:
            cat_name = self.get_category_name(cat["category"])
            total_amt = cat["total"]
            formatted_categories.append({
                "category": cat["category"],
                "label": cat_name,
                "total": total_amt,
                "count": cat["count"],
            })

        budget_summary = await self.get_budget_summary(user_id, timezone_str)

        return {
            "today_total": today_total,
            "week_total": week_total,
            "month_total": month_total,
            "month_income": month_income,
            "net_balance": net_balance,
            "month_title": current_month_title,
            "categories": formatted_categories,
            "budget": budget_summary,
        }

    async def get_budget_summary(
        self,
        user_id: int,
        timezone_str: str = "Asia/Almaty"
    ) -> Dict[str, Any]:
        tz = ZoneInfo(timezone_str)
        now = datetime.now(tz)
        today_str = now.strftime("%Y-%m-%d")
        seven_days_ago_str = (now - timedelta(days=6)).strftime("%Y-%m-%d")
        month_start_str = now.strftime("%Y-%m-01")

        budget = await self.expense_repo.get_budget(user_id)
        weekly_budget = budget.weekly_budget if budget else 0.0
        monthly_budget = budget.monthly_budget if budget else 0.0
        currency = budget.currency if budget else "₸"

        week_spent = await self.expense_repo.get_period_total(user_id, seven_days_ago_str, today_str)
        month_spent = await self.expense_repo.get_period_total(user_id, month_start_str, today_str)

        week_remaining = max(0.0, weekly_budget - week_spent) if weekly_budget > 0 else 0.0
        month_remaining = max(0.0, monthly_budget - month_spent) if monthly_budget > 0 else 0.0

        week_exceeded = max(0.0, week_spent - weekly_budget) if weekly_budget > 0 else 0.0
        month_exceeded = max(0.0, month_spent - monthly_budget) if monthly_budget > 0 else 0.0

        week_pct = round((week_spent / weekly_budget) * 100, 1) if weekly_budget > 0 else 0.0
        month_pct = round((month_spent / monthly_budget) * 100, 1) if monthly_budget > 0 else 0.0

        return {
            "weekly_budget": weekly_budget,
            "monthly_budget": monthly_budget,
            "week_spent": week_spent,
            "month_spent": month_spent,
            "week_remaining": week_remaining,
            "month_remaining": month_remaining,
            "week_exceeded": week_exceeded,
            "month_exceeded": month_exceeded,
            "week_percentage": week_pct,
            "month_percentage": month_pct,
            "currency": currency,
        }
