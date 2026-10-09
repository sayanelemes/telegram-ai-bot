from datetime import datetime
from typing import List, Optional, Dict, Any
import aiosqlite
from app.database.connection import DatabaseManager
from app.database.models import FoodEntryDB, FoodItemDB, DailyNutritionSummary


class FoodRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def create_food_entry(self, entry: FoodEntryDB) -> FoodEntryDB:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "INSERT INTO food_entries (user_id, meal_type, entry_date, entry_time, "
                "total_calories, total_protein, total_fat, total_carbs, advice, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.user_id,
                    entry.meal_type,
                    entry.entry_date,
                    entry.entry_time,
                    entry.total_calories,
                    entry.total_protein,
                    entry.total_fat,
                    entry.total_carbs,
                    entry.advice,
                    entry.created_at or now,
                )
            )
            entry_id = cursor.lastrowid
            entry.id = entry_id

            # Insert items
            for item in entry.items:
                c_item = await conn.execute(
                    "INSERT INTO food_items (food_entry_id, name, portion_g, calories, protein_g, fat_g, carbs_g) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        entry_id,
                        item.name,
                        item.portion_g,
                        item.calories,
                        item.protein_g,
                        item.fat_g,
                        item.carbs_g,
                    )
                )
                item.id = c_item.lastrowid
                item.food_entry_id = entry_id

            await conn.commit()
            return entry

    async def get_entry_by_id(self, entry_id: int) -> Optional[FoodEntryDB]:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT id, user_id, meal_type, entry_date, entry_time, "
                "total_calories, total_protein, total_fat, total_carbs, advice, created_at "
                "FROM food_entries WHERE id = ?",
                (entry_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None

            items_cur = await conn.execute(
                "SELECT id, food_entry_id, name, portion_g, calories, protein_g, fat_g, carbs_g "
                "FROM food_items WHERE food_entry_id = ? ORDER BY id ASC",
                (entry_id,)
            )
            items_rows = await items_cur.fetchall()
            items = [FoodItemDB(**dict(item_r)) for item_r in items_rows]

            entry_dict = dict(row)
            entry_dict["items"] = items
            return FoodEntryDB(**entry_dict)

    async def get_entries_by_date(self, user_id: int, date_str: str) -> List[FoodEntryDB]:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT id, user_id, meal_type, entry_date, entry_time, "
                "total_calories, total_protein, total_fat, total_carbs, advice, created_at "
                "FROM food_entries WHERE user_id = ? AND entry_date = ? "
                "ORDER BY entry_time ASC, id ASC",
                (user_id, date_str)
            )
            rows = await cursor.fetchall()
            entries = []
            for r in rows:
                items_cur = await conn.execute(
                    "SELECT id, food_entry_id, name, portion_g, calories, protein_g, fat_g, carbs_g "
                    "FROM food_items WHERE food_entry_id = ? ORDER BY id ASC",
                    (r["id"],)
                )
                items = [FoodItemDB(**dict(ir)) for ir in await items_cur.fetchall()]
                d = dict(r)
                d["items"] = items
                entries.append(FoodEntryDB(**d))
            return entries

    async def get_daily_totals(self, user_id: int, date_str: str) -> Dict[str, Any]:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(id) as count, "
                "COALESCE(SUM(total_calories), 0) as total_calories, "
                "COALESCE(SUM(total_protein), 0.0) as total_protein, "
                "COALESCE(SUM(total_fat), 0.0) as total_fat, "
                "COALESCE(SUM(total_carbs), 0.0) as total_carbs "
                "FROM food_entries WHERE user_id = ? AND entry_date = ?",
                (user_id, date_str)
            )
            row = await cursor.fetchone()
            if not row:
                return {
                    "count": 0,
                    "calories": 0,
                    "protein": 0.0,
                    "fat": 0.0,
                    "carbs": 0.0
                }
            return {
                "count": row["count"],
                "calories": int(row["total_calories"]),
                "protein": round(float(row["total_protein"]), 1),
                "fat": round(float(row["total_fat"]), 1),
                "carbs": round(float(row["total_carbs"]), 1),
            }

    async def get_history_by_dates(
        self,
        user_id: int,
        limit_days: int = 7,
        offset_days: int = 0
    ) -> List[Dict[str, Any]]:
        """Get summarized history grouped by distinct dates."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT entry_date, "
                "COUNT(id) as meals_count, "
                "COALESCE(SUM(total_calories), 0) as calories, "
                "COALESCE(SUM(total_protein), 0.0) as protein, "
                "COALESCE(SUM(total_fat), 0.0) as fat, "
                "COALESCE(SUM(total_carbs), 0.0) as carbs "
                "FROM food_entries "
                "WHERE user_id = ? "
                "GROUP BY entry_date "
                "ORDER BY entry_date DESC "
                "LIMIT ? OFFSET ?",
                (user_id, limit_days, offset_days)
            )
            rows = await cursor.fetchall()
            results = []
            for r in rows:
                results.append({
                    "date": r["entry_date"],
                    "meals_count": r["meals_count"],
                    "calories": int(r["calories"]),
                    "protein": round(float(r["protein"]), 1),
                    "fat": round(float(r["fat"]), 1),
                    "carbs": round(float(r["carbs"]), 1),
                })
            return results

    async def count_history_days(self, user_id: int) -> int:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(DISTINCT entry_date) as cnt FROM food_entries WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            return row["cnt"] if row else 0

    async def delete_entry(self, entry_id: int, user_id: int) -> bool:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM food_entries WHERE id = ? AND user_id = ?",
                (entry_id, user_id)
            )
            await conn.commit()
            return cursor.rowcount > 0
