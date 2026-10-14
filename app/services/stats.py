from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo
from app.database.repositories.user_repository import UserRepository
from app.database.repositories.food_repository import FoodRepository
from app.database.repositories.expense_repository import ExpenseRepository
from app.services.expenses import ExpenseService


class StatsService:
    def __init__(
        self,
        user_repo: UserRepository,
        food_repo: FoodRepository,
        expense_repo: ExpenseRepository,
    ):
        self.user_repo = user_repo
        self.food_repo = food_repo
        self.expense_repo = expense_repo

    def get_period_dates(self, period: str, tz_str: str) -> tuple[str, str]:
        """Returns (start_date, end_date) for 'day', 'week', 'month' in user's timezone."""
        try:
            tz = ZoneInfo(tz_str)
        except Exception:
            tz = ZoneInfo("Asia/Almaty")
        now = datetime.now(tz)
        today_str = now.strftime("%Y-%m-%d")

        if period == "day":
            return today_str, today_str
        elif period == "week":
            start_str = (now - timedelta(days=6)).strftime("%Y-%m-%d")
            return start_str, today_str
        elif period == "month":
            start_str = now.strftime("%Y-%m-01")
            return start_str, today_str
        else:
            start_str = (now - timedelta(days=6)).strftime("%Y-%m-%d")
            return start_str, today_str

    async def get_nutrition_stats(
        self,
        user_id: int,
        period: str = "week",
        timezone_str: str = "Asia/Almaty"
    ) -> Dict[str, Any]:
        start_date, end_date = self.get_period_dates(period, timezone_str)
        goal = await self.user_repo.get_calorie_goal(user_id)
        target_calories = goal.target_calories if goal else 2000

        stats = await self.food_repo.get_period_nutrition_stats(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            target_calories=target_calories
        )
        stats["period"] = period
        return stats

    async def get_expense_stats(
        self,
        user_id: int,
        period: str = "month",
        timezone_str: str = "Asia/Almaty"
    ) -> Dict[str, Any]:
        start_date, end_date = self.get_period_dates(period, timezone_str)

        avg_check = await self.expense_repo.get_average_check(user_id, start_date, end_date)
        total_spent = await self.expense_repo.get_period_total(user_id, start_date, end_date)

        async with self.expense_repo.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT COUNT(id) as count FROM expenses "
                "WHERE user_id = ? AND expense_date >= ? AND expense_date <= ? AND (entry_type = 'expense' OR entry_type IS NULL)",
                (user_id, start_date, end_date)
            )
            r = await cur.fetchone()
            count = r["count"] if r else 0

        top_cats = await self.expense_repo.get_top_categories(user_id, start_date, end_date, limit=3)
        formatted_top_cats = [
            {
                "category": c["category"],
                "label": ExpenseService.get_category_name(c["category"]),
                "total": c["total"],
                "count": c["count"],
                "percentage": c["percentage"],
            }
            for c in top_cats
        ]

        recurring = await self.expense_repo.get_recurring_expenses(user_id, days=60)

        cat_budgets = await self.expense_repo.get_category_budgets(user_id)
        month_start, _ = self.get_period_dates("month", timezone_str)
        today_str, _ = self.get_period_dates("day", timezone_str)

        for cb in cat_budgets:
            async with self.expense_repo.db.get_connection() as conn:
                c_cur = await conn.execute(
                    "SELECT COALESCE(SUM(amount), 0.0) as total FROM expenses "
                    "WHERE user_id = ? AND category = ? AND expense_date >= ? AND expense_date <= ? AND (entry_type = 'expense' OR entry_type IS NULL)",
                    (user_id, cb["category"], month_start, today_str)
                )
                cr = await c_cur.fetchone()
                cat_spent = float(cr["total"]) if cr else 0.0
            cb["spent"] = cat_spent
            cb["percentage"] = round((cat_spent / cb["monthly_limit"] * 100), 1) if cb["monthly_limit"] > 0 else 0.0

        return {
            "period": period,
            "average_check": avg_check,
            "total_spent": total_spent,
            "total_count": count,
            "top_categories": formatted_top_cats,
            "recurring_expenses": recurring,
            "category_budgets": cat_budgets,
        }

    async def generate_weekly_summary(
        self,
        user_id: int,
        timezone_str: str = "Asia/Almaty"
    ) -> Dict[str, Any]:
        """
        Generate Sunday weekly summary:
        - average calories
        - surplus days count
        - risk / deficit days count (< 90%)
        - expenses by category
        - impulse expenses share
        """
        try:
            tz = ZoneInfo(timezone_str)
        except Exception:
            tz = ZoneInfo("Asia/Almaty")
        now = datetime.now(tz)
        today_str = now.strftime("%Y-%m-%d")
        week_start_str = (now - timedelta(days=6)).strftime("%Y-%m-%d")

        goal = await self.user_repo.get_calorie_goal(user_id)
        target_calories = goal.target_calories if goal else 2000

        # Nutrition
        nutr_stats = await self.food_repo.get_period_nutrition_stats(
            user_id, week_start_str, today_str, target_calories
        )
        avg_cal = nutr_stats["average_calories"]
        surplus_days = nutr_stats["surplus_days_count"]
        risk_days = nutr_stats["risk_days_count"]

        # Expenses
        exp_summary = await self.expense_repo.get_weekly_expense_summary(
            user_id, week_start_str, today_str
        )
        total_exp = exp_summary["total_spent"]
        impulse_tot = exp_summary["impulse_total"]
        impulse_pct = exp_summary["impulse_percentage"]

        top_cats = await self.expense_repo.get_top_categories(user_id, week_start_str, today_str, limit=3)
        formatted_top_cats = [
            {
                "category": c["category"],
                "label": ExpenseService.get_category_name(c["category"]),
                "total": c["total"],
                "count": c["count"],
                "percentage": c["percentage"],
            }
            for c in top_cats
        ]

        top_cat_lines = []
        for c in formatted_top_cats:
            top_cat_lines.append(f"  • {c['label']}: {c['total']:,.0f} ₸ ({c['percentage']}%)")
        cats_str = "\n".join(top_cat_lines) if top_cat_lines else "  • Нет расходов"

        summary_text = (
            f"📊 **Воскресная сводка за неделю ({week_start_str} — {today_str})**\n\n"
            f"🥩 **Питание (набор массы):**\n"
            f"• Средний калораж: **{avg_cal} ккал / день** (норма: {target_calories})\n"
            f"• Дней в профиците: **{surplus_days}** из 7\n"
            f"• Дней с риском недобора (<90%): **{risk_days}**\n\n"
            f"💰 **Финансы:**\n"
            f"• Всего потрачено: **{total_exp:,.0f} ₸**\n"
            f"• Топ категорий:\n{cats_str}\n"
            f"• Импульсивные покупки: **{impulse_tot:,.0f} ₸** ({impulse_pct}% от всех трат)\n"
        )

        return {
            "start_date": week_start_str,
            "end_date": today_str,
            "average_calories": avg_cal,
            "target_calories": target_calories,
            "surplus_days": surplus_days,
            "risk_days": risk_days,
            "total_expenses": total_exp,
            "top_categories": formatted_top_cats,
            "impulse_expenses_total": impulse_tot,
            "impulse_percentage": impulse_pct,
            "summary_text": summary_text,
        }
