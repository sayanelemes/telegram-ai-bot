import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from zoneinfo import ZoneInfo

from app.database.connection import DatabaseManager

logger = logging.getLogger(__name__)


class ProductivityRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    # ==========================
    # TASKS (Задачи)
    # ==========================

    async def get_tasks(
        self,
        user_id: int,
        is_completed: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM tasks WHERE user_id = ?"
        params: list = [user_id]
        if is_completed is not None:
            query += " AND is_completed = ?"
            params.append(1 if is_completed else 0)
        query += " ORDER BY is_completed ASC, CASE priority WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END ASC, due_at ASC, id DESC;"

        async with self.db.get_connection() as conn:
            cur = await conn.execute(query, params)
            rows = await cur.fetchall()
            return [
                {
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "title": r["title"],
                    "due_at": r["due_at"],
                    "priority": r["priority"],
                    "repeat": r["repeat"],
                    "is_completed": bool(r["is_completed"]),
                    "postponed_count": r["postponed_count"] or 0,
                    "completed_at": r["completed_at"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]

    async def create_task(
        self,
        user_id: int,
        title: str,
        due_at: Optional[str] = None,
        priority: str = "normal",
        repeat: str = "none",
    ) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "INSERT INTO tasks (user_id, title, due_at, priority, repeat, is_completed, postponed_count, created_at) "
                "VALUES (?, ?, ?, ?, ?, 0, 0, ?);",
                (user_id, title.strip(), due_at, priority, repeat, now)
            )
            task_id = cur.lastrowid
            await conn.commit()

        return {
            "id": task_id,
            "user_id": user_id,
            "title": title.strip(),
            "due_at": due_at,
            "priority": priority,
            "repeat": repeat,
            "is_completed": False,
            "postponed_count": 0,
            "created_at": now,
        }

    async def update_task(
        self,
        user_id: int,
        task_id: int,
        title: Optional[str] = None,
        due_at: Optional[str] = None,
        priority: Optional[str] = None,
        is_completed: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM tasks WHERE id = ? AND user_id = ?;",
                (task_id, user_id)
            )
            row = await cur.fetchone()
            if not row:
                return None

            new_title = title if title is not None else row["title"]
            new_priority = priority if priority is not None else row["priority"]
            new_is_comp = bool(row["is_completed"]) if is_completed is None else bool(is_completed)
            completed_at = row["completed_at"]
            if is_completed is True and not row["is_completed"]:
                completed_at = datetime.utcnow().isoformat()
            elif is_completed is False:
                completed_at = None

            # Track postponed count if due_at was moved
            curr_due = row["due_at"]
            new_due = due_at if due_at is not None else curr_due
            postponed_count = row["postponed_count"] or 0
            if due_at is not None and curr_due is not None and due_at != curr_due:
                postponed_count += 1

            await conn.execute(
                "UPDATE tasks SET title = ?, due_at = ?, priority = ?, is_completed = ?, "
                "postponed_count = ?, completed_at = ? WHERE id = ? AND user_id = ?;",
                (
                    new_title, new_due, new_priority, 1 if new_is_comp else 0,
                    postponed_count, completed_at, task_id, user_id
                )
            )
            await conn.commit()

            cur2 = await conn.execute("SELECT * FROM tasks WHERE id = ?;", (task_id,))
            res = await cur2.fetchone()
            d = dict(res)
            d["is_completed"] = bool(d["is_completed"])
            return d

    async def postpone_task(
        self,
        user_id: int,
        task_id: int,
        choice: str,
        user_timezone: str = "Asia/Almaty"
    ) -> Optional[Dict[str, Any]]:
        """
        1-tap postpone:
        - "tomorrow": next day 10:00
        - "evening": today 19:00
        - "saturday": upcoming Saturday 11:00
        Increments postponed_count. If >= 3, sets warning flag.
        """
        try:
            tz = ZoneInfo(user_timezone)
        except Exception:
            tz = ZoneInfo("Asia/Almaty")
        now_local = datetime.now(tz=tz)

        if choice == "tomorrow":
            target = (now_local + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        elif choice == "evening":
            target = now_local.replace(hour=19, minute=0, second=0, microsecond=0)
            if target <= now_local:
                target += timedelta(days=1)
        elif choice == "saturday":
            days_ahead = (5 - now_local.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            target = (now_local + timedelta(days=days_ahead)).replace(hour=11, minute=0, second=0, microsecond=0)
        else:
            target = now_local + timedelta(days=1)

        new_due_str = target.isoformat()

        async with self.db.get_connection() as conn:
            cur = await conn.execute("SELECT * FROM tasks WHERE id = ? AND user_id = ?;", (task_id, user_id))
            row = await cur.fetchone()
            if not row:
                return None

            new_count = (row["postponed_count"] or 0) + 1
            await conn.execute(
                "UPDATE tasks SET due_at = ?, postponed_count = ? WHERE id = ? AND user_id = ?;",
                (new_due_str, new_count, task_id, user_id)
            )
            await conn.commit()

            cur2 = await conn.execute("SELECT * FROM tasks WHERE id = ?;", (task_id,))
            res = await cur2.fetchone()
            d = dict(res)
            d["is_completed"] = bool(d["is_completed"])
            d["warning"] = "Удалить или разбить?" if new_count >= 3 else None
            return d

    async def get_top_urgent_tasks(self, user_id: int, limit: int = 3) -> List[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM tasks WHERE user_id = ? AND is_completed = 0 "
                "ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END ASC, due_at ASC, id DESC LIMIT ?;",
                (user_id, limit)
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def delete_task(self, user_id: int, task_id: int) -> bool:
        async with self.db.get_connection() as conn:
            cur = await conn.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?;", (task_id, user_id))
            await conn.commit()
            return cur.rowcount > 0

    # ==========================
    # NOTES (Заметки)
    # ==========================

    async def get_notes(
        self,
        user_id: int,
        query: Optional[str] = None,
        search: Optional[str] = None,
        tag: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        q_term = query or search
        sql = "SELECT * FROM notes WHERE user_id = ?"
        params: list = [user_id]

        if tag:
            sql += " AND tags LIKE ?"
            params.append(f"%{tag.strip()}%")

        if q_term:
            s = f"%{q_term.strip().lower()}%"
            sql += " AND (LOWER(title) LIKE ? OR LOWER(content) LIKE ? OR LOWER(tags) LIKE ?)"
            params.extend([s, s, s])

        sql += " ORDER BY is_pinned DESC, updated_at DESC, id DESC;"

        async with self.db.get_connection() as conn:
            cur = await conn.execute(sql, params)
            rows = await cur.fetchall()
            return [
                {
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "title": r["title"] or "",
                    "content": r["content"],
                    "tags": r["tags"] or "",
                    "is_pinned": bool(r["is_pinned"]),
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
                for r in rows
            ]

    async def create_note(
        self,
        user_id: int,
        title: Optional[str],
        content: str,
        tags: Optional[str] = None,
        is_pinned: bool = False
    ) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "INSERT INTO notes (user_id, title, content, tags, is_pinned, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?);",
                (user_id, title, content, tags, 1 if is_pinned else 0, now, now)
            )
            note_id = cur.lastrowid
            await conn.commit()

        return {
            "id": note_id,
            "user_id": user_id,
            "title": title or "",
            "content": content,
            "tags": tags or "",
            "is_pinned": is_pinned,
            "created_at": now,
            "updated_at": now,
        }

    async def update_note(
        self,
        user_id: int,
        note_id: int,
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[str] = None,
        is_pinned: Optional[bool] = None
    ) -> Optional[Dict[str, Any]]:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            cur = await conn.execute("SELECT * FROM notes WHERE id = ? AND user_id = ?;", (note_id, user_id))
            row = await cur.fetchone()
            if not row:
                return None

            new_title = title if title is not None else row["title"]
            new_content = content if content is not None else row["content"]
            new_tags = tags if tags is not None else row["tags"]
            new_pinned = bool(row["is_pinned"]) if is_pinned is None else bool(is_pinned)

            await conn.execute(
                "UPDATE notes SET title = ?, content = ?, tags = ?, is_pinned = ?, updated_at = ? "
                "WHERE id = ? AND user_id = ?;",
                (new_title, new_content, new_tags, 1 if new_pinned else 0, now, note_id, user_id)
            )
            await conn.commit()

            cur2 = await conn.execute("SELECT * FROM notes WHERE id = ?;", (note_id,))
            res = await cur2.fetchone()
            d = dict(res)
            d["is_pinned"] = bool(d["is_pinned"])
            return d

    async def delete_note(self, user_id: int, note_id: int) -> bool:
        async with self.db.get_connection() as conn:
            cur = await conn.execute("DELETE FROM notes WHERE id = ? AND user_id = ?;", (note_id, user_id))
            await conn.commit()
            return cur.rowcount > 0

    # ==========================
    # HABITS (Привычки и стрики)
    # ==========================

    async def get_habits(self, user_id: int, today_str: str) -> List[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM habits WHERE user_id = ? AND is_active = 1 ORDER BY id ASC;",
                (user_id,)
            )
            rows = await cur.fetchall()

            result = []
            for r in rows:
                habit_id = r["id"]
                cur_log = await conn.execute(
                    "SELECT id FROM habit_logs WHERE habit_id = ? AND log_date = ?;",
                    (habit_id, today_str)
                )
                log_row = await cur_log.fetchone()
                completed_today = log_row is not None

                result.append({
                    "id": habit_id,
                    "user_id": r["user_id"],
                    "name": r["name"],
                    "target_frequency": r["target_frequency"],
                    "streak": r["streak"] or 0,
                    "best_streak": r["best_streak"] or 0,
                    "completed_today": completed_today,
                    "created_at": r["created_at"],
                })

            return result

    async def get_habits_with_status(self, user_id: int, target_date: str) -> List[Dict[str, Any]]:
        return await self.get_habits(user_id, target_date)

    async def create_habit(
        self,
        user_id: int,
        name: str,
        target_frequency: str = "daily"
    ) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "INSERT INTO habits (user_id, name, target_frequency, streak, best_streak, is_active, created_at) "
                "VALUES (?, ?, ?, 0, 0, 1, ?);",
                (user_id, name.strip(), target_frequency, now)
            )
            habit_id = cur.lastrowid
            await conn.commit()

        return {
            "id": habit_id,
            "user_id": user_id,
            "name": name.strip(),
            "target_frequency": target_frequency,
            "streak": 0,
            "best_streak": 0,
            "completed_today": False,
            "created_at": now,
        }

    async def toggle_habit(
        self,
        user_id: int,
        habit_id: int,
        today_str: str,
        yesterday_str: str
    ) -> Optional[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM habits WHERE id = ? AND user_id = ?;",
                (habit_id, user_id)
            )
            habit = await cur.fetchone()
            if not habit:
                return None

            cur_log = await conn.execute(
                "SELECT id FROM habit_logs WHERE habit_id = ? AND log_date = ?;",
                (habit_id, today_str)
            )
            log = await cur_log.fetchone()

            streak = habit["streak"] or 0
            best_streak = habit["best_streak"] or 0

            if log:
                # Untoggle: remove log, decrement streak
                await conn.execute("DELETE FROM habit_logs WHERE id = ?;", (log["id"],))
                new_streak = max(0, streak - 1)
                await conn.execute(
                    "UPDATE habits SET streak = ? WHERE id = ?;",
                    (new_streak, habit_id)
                )
                await conn.commit()
                completed_today = False
            else:
                # Toggle: mark complete
                now = datetime.utcnow().isoformat()
                await conn.execute(
                    "INSERT INTO habit_logs (habit_id, user_id, log_date, created_at) VALUES (?, ?, ?, ?);",
                    (habit_id, user_id, today_str, now)
                )
                # Check if yesterday was completed
                cur_yest = await conn.execute(
                    "SELECT id FROM habit_logs WHERE habit_id = ? AND log_date = ?;",
                    (habit_id, yesterday_str)
                )
                yest_log = await cur_yest.fetchone()

                if yest_log or streak == 0:
                    new_streak = streak + 1
                else:
                    new_streak = 1

                new_best = max(best_streak, new_streak)
                await conn.execute(
                    "UPDATE habits SET streak = ?, best_streak = ? WHERE id = ?;",
                    (new_streak, new_best, habit_id)
                )
                await conn.commit()
                streak = new_streak
                best_streak = new_best
                completed_today = True

        return {
            "id": habit_id,
            "user_id": user_id,
            "name": habit["name"],
            "streak": streak,
            "best_streak": best_streak,
            "completed_today": completed_today,
            "is_completed_today": completed_today,
        }

    async def toggle_habit_log(self, user_id: int, habit_id: int, log_date: str) -> Optional[Dict[str, Any]]:
        try:
            dt = datetime.fromisoformat(log_date)
            yesterday_str = (dt - timedelta(days=1)).date().isoformat()
        except Exception:
            yesterday_str = log_date
        return await self.toggle_habit(user_id, habit_id, log_date, yesterday_str)

    async def get_pending_habits_for_today(self, user_id: int, log_date: str) -> List[Dict[str, Any]]:
        habits = await self.get_habits(user_id, log_date)
        return [h for h in habits if not h["completed_today"]]

    async def delete_habit(self, user_id: int, habit_id: int) -> bool:
        async with self.db.get_connection() as conn:
            cur = await conn.execute("DELETE FROM habits WHERE id = ? AND user_id = ?;", (habit_id, user_id))
            await conn.commit()
            return cur.rowcount > 0

    async def get_habits_at_risk(self, user_id: int, today_str: str) -> List[Dict[str, Any]]:
        """Find habits with an active streak >= 2 that haven't been completed today."""
        habits = await self.get_habits(user_id, today_str)
        return [h for h in habits if h["streak"] >= 2 and not h["completed_today"]]

    # ==========================
    # EVENING CHECK-IN (Чекаут)
    # ==========================

    async def log_checkin(
        self,
        user_id: int,
        log_date: str,
        mood: int,
        energy: int,
        satiety: int = 3,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            await conn.execute(
                "INSERT INTO check_ins (user_id, log_date, mood, energy, satiety, notes, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id, log_date) DO UPDATE SET "
                "mood = excluded.mood, energy = excluded.energy, satiety = excluded.satiety, "
                "notes = excluded.notes;",
                (user_id, log_date, mood, energy, satiety, notes, now)
            )
            await conn.commit()

        return {
            "user_id": user_id,
            "log_date": log_date,
            "mood": mood,
            "energy": energy,
            "satiety": satiety,
            "notes": notes,
        }

    async def save_check_in(
        self,
        user_id: int,
        log_date: str,
        mood: int,
        energy: int,
        satiety: int = 3,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        return await self.log_checkin(user_id, log_date, mood, energy, satiety, notes)

    async def get_checkin(self, user_id: int, log_date: str) -> Optional[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM check_ins WHERE user_id = ? AND log_date = ?;",
                (user_id, log_date)
            )
            row = await cur.fetchone()
            if not row:
                return None
            return dict(row)

    async def get_today_check_in(self, user_id: int, target_date: str) -> Optional[Dict[str, Any]]:
        return await self.get_checkin(user_id, target_date)

    async def get_check_in_history(self, user_id: int, limit: int = 14) -> List[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM check_ins WHERE user_id = ? ORDER BY log_date DESC LIMIT ?;",
                (user_id, limit)
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    # ==========================
    # USER MODES (DND, Sick, Travel)
    # ==========================

    async def get_user_modes(self, user_id: int) -> Dict[str, Any]:
        now_iso = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            cur = await conn.execute("SELECT * FROM user_modes WHERE user_id = ?;", (user_id,))
            row = await cur.fetchone()
            if not row:
                return {
                    "is_dnd": False,
                    "dnd_until": None,
                    "is_sick": False,
                    "sick_until": None,
                    "is_travel": False,
                    "travel_until": None,
                }

            dnd_until = row["do_not_disturb_until"]
            sick_until = row["sick_mode_until"]
            travel_until = row["travel_mode_until"]

            is_dnd = bool(dnd_until and dnd_until > now_iso)
            is_sick = bool(sick_until and sick_until > now_iso)
            is_travel = bool(travel_until and travel_until > now_iso)

            return {
                "is_dnd": is_dnd,
                "dnd_until": dnd_until if is_dnd else None,
                "is_sick": is_sick,
                "sick_until": sick_until if is_sick else None,
                "is_travel": is_travel,
                "travel_until": travel_until if is_travel else None,
            }

    async def get_active_modes(self, user_id: int) -> Dict[str, bool]:
        m = await self.get_user_modes(user_id)
        return {
            "dnd": m.get("is_dnd", False),
            "sick": m.get("is_sick", False),
            "travel": m.get("is_travel", False),
        }

    async def set_mode(
        self,
        user_id: int,
        mode_type: str,
        until_iso: Optional[str]
    ) -> Dict[str, Any]:
        col = {
            "dnd": "do_not_disturb_until",
            "sick": "sick_mode_until",
            "travel": "travel_mode_until",
        }.get(mode_type)
        if not col:
            raise ValueError(f"Unknown mode type: {mode_type}")

        async with self.db.get_connection() as conn:
            await conn.execute(
                f"INSERT INTO user_modes (user_id, {col}) VALUES (?, ?) "
                f"ON CONFLICT(user_id) DO UPDATE SET {col} = excluded.{col};",
                (user_id, until_iso)
            )
            await conn.commit()

        return await self.get_user_modes(user_id)

    async def clear_modes(self, user_id: int) -> Dict[str, Any]:
        async with self.db.get_connection() as conn:
            await conn.execute(
                "INSERT INTO user_modes (user_id, do_not_disturb_until, sick_mode_until, travel_mode_until) "
                "VALUES (?, NULL, NULL, NULL) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "do_not_disturb_until = NULL, sick_mode_until = NULL, travel_mode_until = NULL;",
                (user_id,)
            )
            await conn.commit()
        return await self.get_user_modes(user_id)

    # ==========================
    # SCHEDULES TABLE OPERATIONS
    # ==========================

    async def get_due_schedules(self, now_ts: int) -> List[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM schedules WHERE is_active = 1 AND next_run_at <= ? ORDER BY next_run_at ASC;",
                (now_ts,)
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def save_schedule(
        self,
        user_id: int,
        job_type: str,
        scheduled_time: str,
        next_run_at: int,
        target_id: Optional[int] = None,
        data_json: Optional[str] = None
    ) -> int:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "INSERT INTO schedules (user_id, job_type, target_id, scheduled_time, next_run_at, data_json, is_active, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?);",
                (user_id, job_type, target_id, scheduled_time, next_run_at, data_json, now, now)
            )
            s_id = cur.lastrowid
            await conn.commit()
            return s_id

    async def update_schedule_next_run(self, schedule_id: int, next_run_at: int) -> None:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            await conn.execute(
                "UPDATE schedules SET next_run_at = ?, updated_at = ? WHERE id = ?;",
                (next_run_at, now, schedule_id)
            )
            await conn.commit()

    async def snooze_schedule(self, schedule_id: int, snooze_minutes: int, now_ts: int) -> int:
        new_next = now_ts + (snooze_minutes * 60)
        await self.update_schedule_next_run(schedule_id, new_next)
        return new_next

    async def deactivate_schedule(self, schedule_id: int) -> None:
        async with self.db.get_connection() as conn:
            await conn.execute("UPDATE schedules SET is_active = 0 WHERE id = ?;", (schedule_id,))
            await conn.commit()
