from datetime import datetime
from typing import List, Optional, Dict, Any
import aiosqlite
from app.database.connection import DatabaseManager
from app.database.models import ReminderDB


class ReminderRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def get_user_reminders(self, user_id: int) -> List[ReminderDB]:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT id, user_id, reminder_type, time_str, interval_hours, is_enabled, updated_at "
                "FROM reminders WHERE user_id = ? ORDER BY id ASC",
                (user_id,)
            )
            rows = await cursor.fetchall()
            return [ReminderDB(**dict(r)) for r in rows]

    async def get_reminder(self, user_id: int, reminder_type: str) -> Optional[ReminderDB]:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT id, user_id, reminder_type, time_str, interval_hours, is_enabled, updated_at "
                "FROM reminders WHERE user_id = ? AND reminder_type = ?",
                (user_id, reminder_type)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return ReminderDB(**dict(row))

    async def save_reminder(self, reminder: ReminderDB) -> ReminderDB:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "INSERT INTO reminders (user_id, reminder_type, time_str, interval_hours, is_enabled, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id, reminder_type) DO UPDATE SET "
                "time_str = excluded.time_str, "
                "interval_hours = excluded.interval_hours, "
                "is_enabled = excluded.is_enabled, "
                "updated_at = excluded.updated_at",
                (
                    reminder.user_id,
                    reminder.reminder_type,
                    reminder.time_str,
                    reminder.interval_hours,
                    1 if reminder.is_enabled else 0,
                    now,
                )
            )
            await conn.commit()
            if not reminder.id:
                reminder.id = cursor.lastrowid
            reminder.updated_at = now
            return reminder

    async def toggle_reminder(self, user_id: int, reminder_type: str, is_enabled: bool) -> bool:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "UPDATE reminders SET is_enabled = ?, updated_at = ? "
                "WHERE user_id = ? AND reminder_type = ?",
                (1 if is_enabled else 0, now, user_id, reminder_type)
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def update_reminder_time(
        self,
        user_id: int,
        reminder_type: str,
        time_str: str,
        interval_hours: int = 0
    ) -> bool:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "UPDATE reminders SET time_str = ?, interval_hours = ?, updated_at = ? "
                "WHERE user_id = ? AND reminder_type = ?",
                (time_str, interval_hours, now, user_id, reminder_type)
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def get_all_active_reminders(self) -> List[Dict[str, Any]]:
        """Returns all enabled reminders joined with users' telegram_id and timezone."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT r.id, r.user_id, r.reminder_type, r.time_str, r.interval_hours, "
                "u.telegram_id, u.timezone, u.first_name "
                "FROM reminders r "
                "JOIN users u ON r.user_id = u.id "
                "WHERE r.is_enabled = 1"
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
