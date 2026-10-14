from datetime import datetime
from typing import List, Optional, Dict, Any
import aiosqlite
from app.database.connection import DatabaseManager
from app.database.models import ExpenseDB, ExpenseItemDB, BudgetDB


class ExpenseRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def create_expense(self, expense: ExpenseDB) -> ExpenseDB:
        now = datetime.utcnow().isoformat()
        is_imp = 1 if (expense.is_impulsive or expense.is_impulse) else 0
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "INSERT INTO expenses (user_id, merchant, amount, currency, category, "
                "entry_type, description, raw_text, ai_analysis, is_impulsive, is_impulse, impulse_reason, link_id, source, expense_date, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    expense.user_id,
                    expense.merchant,
                    expense.amount,
                    expense.currency,
                    expense.category,
                    expense.entry_type,
                    expense.description,
                    expense.raw_text,
                    expense.ai_analysis,
                    is_imp,
                    is_imp,
                    expense.impulse_reason,
                    expense.link_id,
                    expense.source or "manual",
                    expense.expense_date,
                    expense.created_at or now,
                )
            )
            expense_id = cursor.lastrowid
            expense.id = expense_id

            for item in expense.items:
                c_item = await conn.execute(
                    "INSERT INTO expense_items (expense_id, name, price, quantity) "
                    "VALUES (?, ?, ?, ?)",
                    (expense_id, item.name, item.price, item.quantity)
                )
                item.id = c_item.lastrowid
                item.expense_id = expense_id

            await conn.commit()
            return expense

    async def get_expense_by_id(self, expense_id: int) -> Optional[ExpenseDB]:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT id, user_id, merchant, amount, currency, category, "
                "entry_type, description, raw_text, ai_analysis, is_impulsive, is_impulse, impulse_reason, link_id, source, expense_date, created_at "
                "FROM expenses WHERE id = ?",
                (expense_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None

            items_cur = await conn.execute(
                "SELECT id, expense_id, name, price, quantity "
                "FROM expense_items WHERE expense_id = ? ORDER BY id ASC",
                (expense_id,)
            )
            items = [ExpenseItemDB(**dict(ir)) for ir in await items_cur.fetchall()]
            data = dict(row)
            data["is_impulsive"] = bool(data.get("is_impulsive", 0) or data.get("is_impulse", 0))
            data["is_impulse"] = data["is_impulsive"]
            data["entry_type"] = data.get("entry_type") or "expense"
            data["items"] = items
            return ExpenseDB(**data)

    async def get_daily_total(self, user_id: int, date_str: str) -> float:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT COALESCE(SUM(amount), 0.0) as total FROM expenses "
                "WHERE user_id = ? AND expense_date = ? AND (entry_type = 'expense' OR entry_type IS NULL)",
                (user_id, date_str)
            )
            row = await cursor.fetchone()
            return float(row["total"]) if row else 0.0

    async def get_period_total(self, user_id: int, start_date: str, end_date: str) -> float:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT COALESCE(SUM(amount), 0.0) as total FROM expenses "
                "WHERE user_id = ? AND expense_date >= ? AND expense_date <= ? AND (entry_type = 'expense' OR entry_type IS NULL)",
                (user_id, start_date, end_date)
            )
            row = await cursor.fetchone()
            return float(row["total"]) if row else 0.0

    async def get_income_period_total(self, user_id: int, start_date: str, end_date: str) -> float:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT COALESCE(SUM(amount), 0.0) as total FROM expenses "
                "WHERE user_id = ? AND expense_date >= ? AND expense_date <= ? AND entry_type = 'income'",
                (user_id, start_date, end_date)
            )
            row = await cursor.fetchone()
            return float(row["total"]) if row else 0.0

    async def get_period_categories(
        self,
        user_id: int,
        start_date: str,
        end_date: str
    ) -> List[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT category, COALESCE(SUM(amount), 0.0) as total, COUNT(id) as count "
                "FROM expenses "
                "WHERE user_id = ? AND expense_date >= ? AND expense_date <= ? AND (entry_type = 'expense' OR entry_type IS NULL) "
                "GROUP BY category "
                "ORDER BY total DESC",
                (user_id, start_date, end_date)
            )
            rows = await cursor.fetchall()
            return [
                {"category": r["category"], "total": float(r["total"]), "count": r["count"]}
                for r in rows
            ]

    async def get_recent_expenses(self, user_id: int, limit: int = 20) -> List[ExpenseDB]:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT id, user_id, merchant, amount, currency, category, "
                "entry_type, description, raw_text, ai_analysis, is_impulsive, is_impulse, impulse_reason, link_id, source, expense_date, created_at "
                "FROM expenses WHERE user_id = ? ORDER BY expense_date DESC, id DESC LIMIT ?",
                (user_id, limit)
            )
            rows = await cursor.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["is_impulsive"] = bool(d.get("is_impulsive", 0) or d.get("is_impulse", 0))
                d["is_impulse"] = d["is_impulsive"]
                d["entry_type"] = d.get("entry_type") or "expense"
                result.append(ExpenseDB(**d))
            return result

    async def delete_expense(self, expense_id: int, user_id: int) -> bool:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM expenses WHERE id = ? AND user_id = ?",
                (expense_id, user_id)
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def get_budget(self, user_id: int) -> Optional[BudgetDB]:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT id, user_id, weekly_budget, monthly_budget, currency, impulse_monthly_limit, updated_at "
                "FROM budgets WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return BudgetDB(**dict(row))

    async def save_budget(
        self,
        user_id: int,
        weekly_budget: float,
        monthly_budget: float,
        currency: str = "₸",
        impulse_monthly_limit: float = 0.0
    ) -> BudgetDB:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            await conn.execute(
                "INSERT INTO budgets (user_id, weekly_budget, monthly_budget, currency, impulse_monthly_limit, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "weekly_budget = excluded.weekly_budget, "
                "monthly_budget = excluded.monthly_budget, "
                "currency = excluded.currency, "
                "impulse_monthly_limit = excluded.impulse_monthly_limit, "
                "updated_at = excluded.updated_at",
                (user_id, weekly_budget, monthly_budget, currency, impulse_monthly_limit, now)
            )
            await conn.commit()
            return BudgetDB(
                user_id=user_id,
                weekly_budget=weekly_budget,
                monthly_budget=monthly_budget,
                currency=currency,
                impulse_monthly_limit=impulse_monthly_limit,
                updated_at=now
            )

    async def get_average_check(self, user_id: int, start_date: str, end_date: str) -> float:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT COALESCE(AVG(amount), 0.0) as avg_amount "
                "FROM expenses "
                "WHERE user_id = ? AND expense_date >= ? AND expense_date <= ? AND (entry_type = 'expense' OR entry_type IS NULL)",
                (user_id, start_date, end_date)
            )
            row = await cursor.fetchone()
            return round(float(row["avg_amount"]), 2) if row else 0.0

    async def get_top_categories(
        self,
        user_id: int,
        start_date: str,
        end_date: str,
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        total_period = await self.get_period_total(user_id, start_date, end_date)
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT category, COALESCE(SUM(amount), 0.0) as total, COUNT(id) as count "
                "FROM expenses "
                "WHERE user_id = ? AND expense_date >= ? AND expense_date <= ? AND (entry_type = 'expense' OR entry_type IS NULL) "
                "GROUP BY category "
                "ORDER BY total DESC "
                "LIMIT ?",
                (user_id, start_date, end_date, limit)
            )
            rows = await cursor.fetchall()
            result = []
            for r in rows:
                tot = float(r["total"])
                pct = round((tot / total_period * 100), 1) if total_period > 0 else 0.0
                result.append({
                    "category": r["category"],
                    "total": tot,
                    "count": r["count"],
                    "percentage": pct
                })
            return result

    async def get_recurring_expenses(self, user_id: int, days: int = 60) -> List[Dict[str, Any]]:
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT merchant, amount, category, COUNT(id) as occurrences, MAX(expense_date) as last_date "
                "FROM expenses "
                "WHERE user_id = ? AND expense_date >= ? AND (entry_type = 'expense' OR entry_type IS NULL) "
                "GROUP BY LOWER(TRIM(merchant)), amount "
                "HAVING COUNT(id) >= 2 "
                "ORDER BY occurrences DESC, last_date DESC",
                (user_id, cutoff)
            )
            rows = await cursor.fetchall()
            return [
                {
                    "merchant": r["merchant"],
                    "amount": float(r["amount"]),
                    "category": r["category"],
                    "occurrences": r["occurrences"],
                    "last_date": r["last_date"],
                }
                for r in rows
            ]

    async def get_category_budgets(self, user_id: int) -> List[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT id, user_id, category, monthly_limit, alert_80_sent, alert_100_sent, updated_at "
                "FROM category_budgets WHERE user_id = ? ORDER BY monthly_limit DESC",
                (user_id,)
            )
            rows = await cur.fetchall()
            return [
                {
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "category": r["category"],
                    "monthly_limit": float(r["monthly_limit"]),
                    "alert_80_sent": bool(r["alert_80_sent"]),
                    "alert_100_sent": bool(r["alert_100_sent"]),
                    "updated_at": r["updated_at"],
                }
                for r in rows
            ]

    async def save_category_budget(self, user_id: int, category: str, monthly_limit: float) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        clean_cat = category.strip().lower()
        async with self.db.get_connection() as conn:
            await conn.execute(
                "INSERT INTO category_budgets (user_id, category, monthly_limit, alert_80_sent, alert_100_sent, updated_at) "
                "VALUES (?, ?, ?, 0, 0, ?) "
                "ON CONFLICT(user_id, category) DO UPDATE SET "
                "monthly_limit = excluded.monthly_limit, "
                "updated_at = excluded.updated_at",
                (user_id, clean_cat, monthly_limit, now)
            )
            await conn.commit()
            return {
                "user_id": user_id,
                "category": clean_cat,
                "monthly_limit": monthly_limit,
                "updated_at": now
            }

    async def delete_category_budget(self, user_id: int, category: str) -> bool:
        clean_cat = category.strip().lower()
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "DELETE FROM category_budgets WHERE user_id = ? AND category = ?",
                (user_id, clean_cat)
            )
            await conn.commit()
            return cur.rowcount > 0

    async def check_category_budget_alert(
        self,
        user_id: int,
        category: str,
        month_start_date: str,
        current_date: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check if spent in category exceeds 80% or 100% of budget.
        Triggers alert at most once per threshold crossing.
        """
        clean_cat = category.strip().lower()
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT monthly_limit, alert_80_sent, alert_100_sent FROM category_budgets "
                "WHERE user_id = ? AND category = ?",
                (user_id, clean_cat)
            )
            row = await cur.fetchone()
            if not row or row["monthly_limit"] <= 0:
                return None

            limit = float(row["monthly_limit"])
            alert_80 = bool(row["alert_80_sent"])
            alert_100 = bool(row["alert_100_sent"])

            cur_spent = await conn.execute(
                "SELECT COALESCE(SUM(amount), 0.0) as total FROM expenses "
                "WHERE user_id = ? AND category = ? AND expense_date >= ? AND expense_date <= ? AND (entry_type = 'expense' OR entry_type IS NULL)",
                (user_id, clean_cat, month_start_date, current_date)
            )
            s_row = await cur_spent.fetchone()
            spent = float(s_row["total"]) if s_row else 0.0

            pct = (spent / limit) * 100

            if pct >= 100 and not alert_100:
                await conn.execute(
                    "UPDATE category_budgets SET alert_100_sent = 1, alert_80_sent = 1 WHERE user_id = ? AND category = ?",
                    (user_id, clean_cat)
                )
                await conn.commit()
                return {
                    "threshold": 100,
                    "category": clean_cat,
                    "spent": spent,
                    "limit": limit,
                    "percentage": round(pct, 1),
                    "message": f"Лимит по категории '{clean_cat}' исчерпан на 100%! Потрачено {spent:.0f} из {limit:.0f} ₸"
                }
            elif pct >= 80 and not alert_80:
                await conn.execute(
                    "UPDATE category_budgets SET alert_80_sent = 1 WHERE user_id = ? AND category = ?",
                    (user_id, clean_cat)
                )
                await conn.commit()
                return {
                    "threshold": 80,
                    "category": clean_cat,
                    "spent": spent,
                    "limit": limit,
                    "percentage": round(pct, 1),
                    "message": f"Внимание: категория '{clean_cat}' достигла {pct:.1f}% от лимита ({spent:.0f} / {limit:.0f} ₸)!"
                }

            return None

    async def export_expenses_csv(
        self,
        user_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> str:
        """Export expenses as CSV string with UTF-8 BOM."""
        import csv
        import io

        query = (
            "SELECT e.id, e.expense_date, e.merchant, e.category, e.amount, e.currency, "
            "e.entry_type, e.is_impulse, e.is_impulsive, e.impulse_reason, e.description, e.source "
            "FROM expenses e WHERE e.user_id = ?"
        )
        params: list = [user_id]
        if start_date:
            query += " AND e.expense_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND e.expense_date <= ?"
            params.append(end_date)
        query += " ORDER BY e.expense_date DESC, e.id DESC"

        async with self.db.get_connection() as conn:
            cur = await conn.execute(query, params)
            expenses = await cur.fetchall()

            output = io.StringIO()
            output.write("\ufeff")
            writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
            writer.writerow([
                "ID", "Дата", "Магазин/Получатель", "Категория", "Сумма", "Валюта",
                "Тип", "Импульсивная", "Причина импульса", "Описание", "Источник"
            ])

            for exp in expenses:
                is_imp = "Да" if (exp["is_impulse"] or exp["is_impulsive"]) else "Нет"
                writer.writerow([
                    exp["id"],
                    exp["expense_date"],
                    exp["merchant"],
                    exp["category"],
                    f"{exp['amount']:.2f}",
                    exp["currency"],
                    exp["entry_type"],
                    is_imp,
                    exp["impulse_reason"] or "",
                    exp["description"] or "",
                    exp["source"] or "manual",
                ])

            return output.getvalue()

    async def get_weekly_expense_summary(
        self,
        user_id: int,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT COALESCE(SUM(amount), 0.0) as total, COUNT(id) as count "
                "FROM expenses WHERE user_id = ? AND expense_date >= ? AND expense_date <= ? AND (entry_type = 'expense' OR entry_type IS NULL)",
                (user_id, start_date, end_date)
            )
            r_tot = await cur.fetchone()
            total_spent = float(r_tot["total"]) if r_tot else 0.0
            total_count = r_tot["count"] if r_tot else 0

            cur_imp = await conn.execute(
                "SELECT COALESCE(SUM(amount), 0.0) as impulse_total, COUNT(id) as impulse_count "
                "FROM expenses WHERE user_id = ? AND expense_date >= ? AND expense_date <= ? "
                "AND (entry_type = 'expense' OR entry_type IS NULL) AND (is_impulse = 1 OR is_impulsive = 1)",
                (user_id, start_date, end_date)
            )
            r_imp = await cur_imp.fetchone()
            impulse_total = float(r_imp["impulse_total"]) if r_imp else 0.0
            impulse_count = r_imp["impulse_count"] if r_imp else 0

            categories = await self.get_period_categories(user_id, start_date, end_date)
            impulse_pct = round((impulse_total / total_spent * 100), 1) if total_spent > 0 else 0.0

            return {
                "start_date": start_date,
                "end_date": end_date,
                "total_spent": total_spent,
                "total_count": total_count,
                "impulse_total": impulse_total,
                "impulse_count": impulse_count,
                "impulse_percentage": impulse_pct,
                "categories": categories,
            }
