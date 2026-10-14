import logging
from app.database.connection import DatabaseManager

logger = logging.getLogger(__name__)


class GeminiUsageRepository:
    def __init__(self, db: DatabaseManager):
        self.db = db

    async def get_user_usage_today(self, user_id: int, date_str: str) -> int:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT call_count FROM gemini_usage WHERE user_id = ? AND call_date = ?;",
                (user_id, date_str)
            )
            row = await cur.fetchone()
            return int(row["call_count"]) if row else 0

    async def get_global_usage_today(self, date_str: str) -> int:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT SUM(call_count) as total FROM gemini_usage WHERE call_date = ?;",
                (date_str,)
            )
            row = await cur.fetchone()
            return int(row["total"]) if row and row["total"] is not None else 0

    async def increment_usage(self, user_id: int, date_str: str) -> int:
        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO gemini_usage (user_id, call_date, call_count)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id, call_date)
                DO UPDATE SET call_count = call_count + 1;
                """,
                (user_id, date_str)
            )
            await conn.commit()
            return await self.get_user_usage_today(user_id, date_str)
