import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from app.database.connection import DatabaseManager

logger = logging.getLogger(__name__)


class WorkoutRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def save_plan(
        self,
        user_id: int,
        name: str,
        days_per_week: int,
        plan_data_json: str,
        is_active: int = 1,
    ) -> int:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            if is_active:
                await conn.execute("UPDATE workout_plans SET is_active = 0 WHERE user_id = ?;", (user_id,))

            cur = await conn.execute(
                "INSERT INTO workout_plans (user_id, name, days_per_week, plan_data_json, is_active, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?);",
                (user_id, name.strip(), days_per_week, plan_data_json, is_active, now, now)
            )
            plan_id = cur.lastrowid
            await conn.commit()
            return plan_id

    async def get_active_plan(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM workout_plans WHERE user_id = ? AND is_active = 1 ORDER BY id DESC LIMIT 1;",
                (user_id,)
            )
            row = await cur.fetchone()
            if not row:
                return None

            d = dict(row)
            try:
                d["plan_data"] = json.loads(d["plan_data_json"])
            except Exception:
                d["plan_data"] = {}
            return d

    async def update_plan_json(
        self,
        user_id: int,
        plan_id: int,
        plan_data_json: str,
        name: Optional[str] = None
    ) -> bool:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            if name:
                cur = await conn.execute(
                    "UPDATE workout_plans SET name = ?, plan_data_json = ?, updated_at = ? WHERE id = ? AND user_id = ?;",
                    (name, plan_data_json, now, plan_id, user_id)
                )
            else:
                cur = await conn.execute(
                    "UPDATE workout_plans SET plan_data_json = ?, updated_at = ? WHERE id = ? AND user_id = ?;",
                    (plan_data_json, now, plan_id, user_id)
                )
            await conn.commit()
            return cur.rowcount > 0

    async def log_exercise(
        self,
        user_id: int,
        workout_date: str,
        exercise_name: str,
        weight_kg: float,
        reps: int,
        sets: int,
        rpe: Optional[float] = None,
        raw_text: Optional[str] = None
    ) -> Dict[str, Any]:
        clean_name = exercise_name.strip()
        now = datetime.utcnow().isoformat()

        async with self.db.get_connection() as conn:
            # Check PR condition: max weight previously logged for this exercise
            cur_pr = await conn.execute(
                "SELECT MAX(weight_kg) as max_w FROM workout_logs WHERE user_id = ? AND LOWER(exercise_name) = LOWER(?);",
                (user_id, clean_name)
            )
            row_pr = await cur_pr.fetchone()
            prev_max = row_pr["max_w"] if row_pr and row_pr["max_w"] is not None else 0.0

            is_pr = 1 if (weight_kg > prev_max and weight_kg > 0) else 0

            cur = await conn.execute(
                "INSERT INTO workout_logs (user_id, workout_date, exercise_name, weight_kg, reps, sets, rpe, is_pr, raw_text, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                (user_id, workout_date, clean_name, weight_kg, reps, sets, rpe, is_pr, raw_text, now)
            )
            log_id = cur.lastrowid
            await conn.commit()

        volume = round(weight_kg * reps * sets, 1)
        return {
            "id": log_id,
            "user_id": user_id,
            "workout_date": workout_date,
            "exercise_name": clean_name,
            "weight_kg": weight_kg,
            "reps": reps,
            "sets": sets,
            "rpe": rpe,
            "is_pr": bool(is_pr),
            "prev_max_weight": prev_max,
            "volume_kg": volume,
            "raw_text": raw_text,
            "created_at": now,
        }

    async def get_workout_history(
        self,
        user_id: int,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM workout_logs WHERE user_id = ? ORDER BY workout_date DESC, id DESC LIMIT ?;",
                (user_id, limit)
            )
            rows = await cur.fetchall()
            return [
                {
                    **dict(r),
                    "is_pr": bool(r["is_pr"]),
                    "volume_kg": round(r["weight_kg"] * r["reps"] * r["sets"], 1),
                }
                for r in rows
            ]

    async def get_exercise_history(
        self,
        user_id: int,
        exercise_name: str,
        limit: int = 30
    ) -> List[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM workout_logs WHERE user_id = ? AND LOWER(exercise_name) = LOWER(?) "
                "ORDER BY workout_date ASC, id ASC LIMIT ?;",
                (user_id, exercise_name.strip(), limit)
            )
            rows = await cur.fetchall()
            return [
                {
                    **dict(r),
                    "is_pr": bool(r["is_pr"]),
                    "volume_kg": round(r["weight_kg"] * r["reps"] * r["sets"], 1),
                }
                for r in rows
            ]

    async def get_user_prs(self, user_id: int) -> List[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT exercise_name, MAX(weight_kg) as max_weight, reps, sets, workout_date "
                "FROM workout_logs WHERE user_id = ? GROUP BY LOWER(exercise_name) ORDER BY max_weight DESC;",
                (user_id,)
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def has_workout_today(self, user_id: int, date_str: str) -> bool:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT COUNT(id) as count FROM workout_logs WHERE user_id = ? AND workout_date = ?;",
                (user_id, date_str)
            )
            row = await cur.fetchone()
            return (row["count"] or 0) > 0

    async def get_total_volume_for_day(self, user_id: int, date_str: str) -> float:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT SUM(weight_kg * reps * sets) as total_vol FROM workout_logs WHERE user_id = ? AND workout_date = ?;",
                (user_id, date_str)
            )
            row = await cur.fetchone()
            return round(row["total_vol"] or 0.0, 1)
