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
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "INSERT INTO expenses (user_id, merchant, amount, currency, category, "
                "entry_type, description, raw_text, ai_analysis, is_impulsive, expense_date, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    1 if expense.is_impulsive else 0,
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
                "entry_type, description, raw_text, ai_analysis, is_impulsive, expense_date, created_at "
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
            data["is_impulsive"] = bool(data.get("is_impulsive", 0))
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
                "entry_type, description, raw_text, ai_analysis, is_impulsive, expense_date, created_at "
                "FROM expenses WHERE user_id = ? ORDER BY expense_date DESC, id DESC LIMIT ?",
                (user_id, limit)
            )
            rows = await cursor.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["is_impulsive"] = bool(d.get("is_impulsive", 0))
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
                "SELECT id, user_id, weekly_budget, monthly_budget, currency, updated_at "
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
        currency: str = "₸"
    ) -> BudgetDB:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            await conn.execute(
                "INSERT INTO budgets (user_id, weekly_budget, monthly_budget, currency, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "weekly_budget = excluded.weekly_budget, "
                "monthly_budget = excluded.monthly_budget, "
                "currency = excluded.currency, "
                "updated_at = excluded.updated_at",
                (user_id, weekly_budget, monthly_budget, currency, now)
            )
            await conn.commit()
            return BudgetDB(
                user_id=user_id,
                weekly_budget=weekly_budget,
                monthly_budget=monthly_budget,
                currency=currency,
                updated_at=now
            )
