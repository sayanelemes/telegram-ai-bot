import math
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from app.database.connection import DatabaseManager
from app.utils.formatters import format_currency, generate_progress_bar

logger = logging.getLogger(__name__)


class FinanceRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    # ==========================
    # SAVINGS GOALS (Цели накоплений)
    # ==========================

    async def create_savings_goal(
        self,
        user_id: int,
        title: str,
        target_amount: float,
        current_amount: float = 0.0,
        monthly_deposit: float = 0.0,
        currency: str = "₸",
        target_date: Optional[str] = None
    ) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "INSERT INTO savings_goals (user_id, title, target_amount, current_amount, monthly_deposit, currency, target_date, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
                (user_id, title.strip(), target_amount, current_amount, monthly_deposit, currency, target_date, now)
            )
            goal_id = cur.lastrowid
            await conn.commit()

        return await self.get_savings_goal_by_id(user_id, goal_id)

    async def get_savings_goal_by_id(self, user_id: int, goal_id: int) -> Optional[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute("SELECT * FROM savings_goals WHERE id = ? AND user_id = ?;", (goal_id, user_id))
            row = await cur.fetchone()
            if not row:
                return None
            return self._enrich_goal(dict(row))

    async def get_savings_goals(self, user_id: int) -> List[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute("SELECT * FROM savings_goals WHERE user_id = ? ORDER BY id DESC;", (user_id,))
            rows = await cur.fetchall()
            return [self._enrich_goal(dict(r)) for r in rows]

    async def deposit_to_savings_goal(
        self,
        user_id: int,
        goal_id: int,
        amount: float
    ) -> Optional[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute("SELECT current_amount, target_amount FROM savings_goals WHERE id = ? AND user_id = ?;", (goal_id, user_id))
            row = await cur.fetchone()
            if not row:
                return None
            new_curr = round(row["current_amount"] + amount, 2)
            await conn.execute("UPDATE savings_goals SET current_amount = ? WHERE id = ? AND user_id = ?;", (new_curr, goal_id, user_id))
            await conn.commit()
        return await self.get_savings_goal_by_id(user_id, goal_id)

    async def delete_savings_goal(self, user_id: int, goal_id: int) -> bool:
        async with self.db.get_connection() as conn:
            cur = await conn.execute("DELETE FROM savings_goals WHERE id = ? AND user_id = ?;", (goal_id, user_id))
            await conn.commit()
            return cur.rowcount > 0

    def _enrich_goal(self, goal: Dict[str, Any]) -> Dict[str, Any]:
        curr = goal.get("current_amount", 0.0)
        target = goal.get("target_amount", 0.0)
        monthly = goal.get("monthly_deposit", 0.0)
        curr_symbol = goal.get("currency", "₸")

        pct = min(100.0, round((curr / target * 100), 1)) if target > 0 else 0.0
        rem = max(0.0, round(target - curr, 2))

        estimated_months = None
        if monthly > 0 and rem > 0:
            estimated_months = math.ceil(rem / monthly)

        progress_bar = generate_progress_bar(curr, target, length=12)

        return {
            **goal,
            "progress_percent": pct,
            "progress_bar": progress_bar,
            "remaining_amount": rem,
            "formatted_current": format_currency(curr, curr_symbol),
            "formatted_target": format_currency(target, curr_symbol),
            "formatted_remaining": format_currency(rem, curr_symbol),
            "estimated_months_to_goal": estimated_months,
        }

    # ==========================
    # SUBSCRIPTIONS (Подписки)
    # ==========================

    async def create_subscription(
        self,
        user_id: int,
        name: str,
        amount: float,
        next_payment_date: str,
        currency: str = "₸",
        billing_cycle: str = "monthly",
    ) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "INSERT INTO subscriptions (user_id, name, amount, currency, billing_cycle, next_payment_date, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?);",
                (user_id, name.strip(), amount, currency, billing_cycle, next_payment_date, now)
            )
            sub_id = cur.lastrowid
            await conn.commit()

        return await self.get_subscription_by_id(user_id, sub_id)

    async def get_subscription_by_id(self, user_id: int, sub_id: int) -> Optional[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute("SELECT * FROM subscriptions WHERE id = ? AND user_id = ?;", (sub_id, user_id))
            row = await cur.fetchone()
            if not row:
                return None
            return self._enrich_subscription(dict(row))

    async def get_subscriptions(self, user_id: int) -> List[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute("SELECT * FROM subscriptions WHERE user_id = ? ORDER BY next_payment_date ASC;", (user_id,))
            rows = await cur.fetchall()
            return [self._enrich_subscription(dict(r)) for r in rows]

    async def update_subscription_next_date(self, user_id: int, sub_id: int, next_payment_date: str) -> bool:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "UPDATE subscriptions SET next_payment_date = ? WHERE id = ? AND user_id = ?;",
                (next_payment_date, sub_id, user_id)
            )
            await conn.commit()
            return cur.rowcount > 0

    async def delete_subscription(self, user_id: int, sub_id: int) -> bool:
        async with self.db.get_connection() as conn:
            cur = await conn.execute("DELETE FROM subscriptions WHERE id = ? AND user_id = ?;", (sub_id, user_id))
            await conn.commit()
            return cur.rowcount > 0

    async def get_subscriptions_due_on(self, target_date: str) -> List[Dict[str, Any]]:
        """Used by scheduler to find subscriptions due on specific date (e.g. tomorrow)."""
        async with self.db.get_connection() as conn:
            cur = await conn.execute("SELECT * FROM subscriptions WHERE next_payment_date = ?;", (target_date,))
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    def _enrich_subscription(self, sub: Dict[str, Any]) -> Dict[str, Any]:
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        next_d = sub.get("next_payment_date", today_str)
        try:
            d_next = datetime.strptime(next_d, "%Y-%m-%d").date()
            d_today = datetime.strptime(today_str, "%Y-%m-%d").date()
            days_left = (d_next - d_today).days
        except Exception:
            days_left = 30

        return {
            **sub,
            "days_until_payment": days_left,
            "is_due_soon": (0 <= days_left <= 1),
            "formatted_amount": format_currency(sub.get("amount", 0.0), sub.get("currency", "₸")),
        }

    # ==========================
    # DEBTS (Долги: мне должны / я должен)
    # ==========================

    async def create_debt(
        self,
        user_id: int,
        person_name: str,
        amount: float,
        direction: str,  # 'i_owe' | 'they_owe'
        currency: str = "₸",
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "INSERT INTO debts (user_id, person_name, amount, currency, direction, description, is_settled, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 0, ?);",
                (user_id, person_name.strip(), amount, currency, direction, description, now)
            )
            debt_id = cur.lastrowid
            await conn.commit()

        return await self.get_debt_by_id(user_id, debt_id)

    async def get_debt_by_id(self, user_id: int, debt_id: int) -> Optional[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute("SELECT * FROM debts WHERE id = ? AND user_id = ?;", (debt_id, user_id))
            row = await cur.fetchone()
            if not row:
                return None
            return self._enrich_debt(dict(row))

    async def get_debts(self, user_id: int, is_settled: Optional[bool] = None) -> Dict[str, Any]:
        query = "SELECT * FROM debts WHERE user_id = ?"
        params: list = [user_id]
        if is_settled is not None:
            query += " AND is_settled = ?"
            params.append(1 if is_settled else 0)
        query += " ORDER BY is_settled ASC, id DESC;"

        async with self.db.get_connection() as conn:
            cur = await conn.execute(query, params)
            rows = await cur.fetchall()

            items = [self._enrich_debt(dict(r)) for r in rows]

            # Calculate totals for unsettled debts
            total_i_owe = sum(d["amount"] for d in items if not d["is_settled"] and d["direction"] == "i_owe")
            total_they_owe = sum(d["amount"] for d in items if not d["is_settled"] and d["direction"] == "they_owe")
            net_balance = round(total_they_owe - total_i_owe, 2)

            return {
                "items": items,
                "total_i_owe": round(total_i_owe, 2),
                "total_they_owe": round(total_they_owe, 2),
                "net_balance": net_balance,
                "formatted_i_owe": format_currency(total_i_owe, "₸"),
                "formatted_they_owe": format_currency(total_they_owe, "₸"),
                "formatted_net_balance": format_currency(net_balance, "₸"),
            }

    async def partial_repay_debt(self, user_id: int, debt_id: int, repay_amount: float) -> Optional[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute("SELECT * FROM debts WHERE id = ? AND user_id = ?;", (debt_id, user_id))
            row = await cur.fetchone()
            if not row:
                return None

            curr_amount = row["amount"]
            new_amount = max(0.0, round(curr_amount - repay_amount, 2))
            is_settled = 1 if new_amount <= 0.0 else 0
            settled_at = datetime.utcnow().isoformat() if is_settled else None

            await conn.execute(
                "UPDATE debts SET amount = ?, is_settled = ?, settled_at = ? WHERE id = ? AND user_id = ?;",
                (new_amount, is_settled, settled_at, debt_id, user_id)
            )
            await conn.commit()

        return await self.get_debt_by_id(user_id, debt_id)

    async def settle_debt_one_tap(self, user_id: int, debt_id: int) -> Optional[Dict[str, Any]]:
        """1-tap close/settle debt."""
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "UPDATE debts SET is_settled = 1, settled_at = ?, amount = 0.0 WHERE id = ? AND user_id = ?;",
                (now, debt_id, user_id)
            )
            await conn.commit()
            if cur.rowcount == 0:
                return None
        return await self.get_debt_by_id(user_id, debt_id)

    async def delete_debt(self, user_id: int, debt_id: int) -> bool:
        async with self.db.get_connection() as conn:
            cur = await conn.execute("DELETE FROM debts WHERE id = ? AND user_id = ?;", (debt_id, user_id))
            await conn.commit()
            return cur.rowcount > 0

    def _enrich_debt(self, debt: Dict[str, Any]) -> Dict[str, Any]:
        curr = debt.get("currency", "₸")
        amt = debt.get("amount", 0.0)
        return {
            **debt,
            "is_settled": bool(debt.get("is_settled")),
            "formatted_amount": format_currency(amt, curr),
        }
