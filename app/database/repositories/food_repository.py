from datetime import datetime, timedelta
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
            # Check link_id
            cur = await conn.execute("SELECT link_id FROM food_entries WHERE id = ? AND user_id = ?;", (entry_id, user_id))
            row = await cur.fetchone()
            if not row:
                return False

            link_id = row["link_id"]
            if link_id:
                # Also delete linked expense atomically
                await conn.execute("DELETE FROM expenses WHERE link_id = ? AND user_id = ?;", (link_id, user_id))

            cursor = await conn.execute(
                "DELETE FROM food_entries WHERE id = ? AND user_id = ?",
                (entry_id, user_id)
            )
            await conn.commit()
            return cursor.rowcount > 0

    # --- Stage 4 Enhancements ---

    async def update_item_portion(
        self,
        entry_id: int,
        item_id: int,
        new_portion_g: float,
        user_id: int
    ) -> Optional[FoodEntryDB]:
        """
        Updates portion of an item in grams and recalculates macros proportionately.
        """
        if new_portion_g <= 0:
            return None

        async with self.db.get_connection() as conn:
            # Verify entry belongs to user
            check_cur = await conn.execute("SELECT id FROM food_entries WHERE id = ? AND user_id = ?;", (entry_id, user_id))
            if not await check_cur.fetchone():
                return None

            item_cur = await conn.execute(
                "SELECT portion_g, calories, protein_g, fat_g, carbs_g FROM food_items WHERE id = ? AND food_entry_id = ?;",
                (item_id, entry_id)
            )
            item_row = await item_cur.fetchone()
            if not item_row:
                return None

            old_portion = float(item_row["portion_g"]) or 1.0
            ratio = new_portion_g / old_portion

            new_cals = max(0, int(round(item_row["calories"] * ratio)))
            new_p = max(0.0, round(item_row["protein_g"] * ratio, 1))
            new_f = max(0.0, round(item_row["fat_g"] * ratio, 1))
            new_c = max(0.0, round(item_row["carbs_g"] * ratio, 1))

            await conn.execute(
                """
                UPDATE food_items
                SET portion_g = ?, calories = ?, protein_g = ?, fat_g = ?, carbs_g = ?
                WHERE id = ?;
                """,
                (new_portion_g, new_cals, new_p, new_f, new_c, item_id)
            )

            # Recalculate totals on food_entries
            sum_cur = await conn.execute(
                """
                SELECT SUM(calories) as total_c, SUM(protein_g) as total_p, SUM(fat_g) as total_f, SUM(carbs_g) as total_c_g
                FROM food_items WHERE food_entry_id = ?;
                """,
                (entry_id,)
            )
            sums = await sum_cur.fetchone()
            await conn.execute(
                """
                UPDATE food_entries
                SET total_calories = ?, total_protein = ?, total_fat = ?, total_carbs = ?
                WHERE id = ?;
                """,
                (
                    sums["total_c"] or 0,
                    round(sums["total_p"] or 0.0, 1),
                    round(sums["total_f"] or 0.0, 1),
                    round(sums["total_c_g"] or 0.0, 1),
                    entry_id
                )
            )
            await conn.commit()

        return await self.get_entry_by_id(entry_id)

    async def repeat_yesterday_entries(
        self,
        user_id: int,
        today_str: str,
        yesterday_str: str
    ) -> List[FoodEntryDB]:
        """Copies all yesterday's meals into today for rapid bulking logging."""
        yesterday_entries = await self.get_entries_by_date(user_id, yesterday_str)
        created = []
        for old_entry in yesterday_entries:
            new_entry = FoodEntryDB(
                user_id=user_id,
                meal_type=old_entry.meal_type,
                entry_date=today_str,
                entry_time=old_entry.entry_time,
                total_calories=old_entry.total_calories,
                total_protein=old_entry.total_protein,
                total_fat=old_entry.total_fat,
                total_carbs=old_entry.total_carbs,
                advice=old_entry.advice,
                items=[
                    FoodItemDB(
                        name=it.name,
                        portion_g=it.portion_g,
                        calories=it.calories,
                        protein_g=it.protein_g,
                        fat_g=it.fat_g,
                        carbs_g=it.carbs_g,
                    ) for it in old_entry.items
                ]
            )
            res = await self.create_food_entry(new_entry)
            created.append(res)
        return created

    # --- Custom Foods & Favorites ---

    async def create_custom_food(
        self,
        user_id: int,
        name: str,
        calories_per_100g: int,
        protein_per_100g: float,
        fat_per_100g: float,
        carbs_per_100g: float,
        is_favorite: bool = False
    ) -> int:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                """
                INSERT INTO custom_foods (
                    user_id, name, calories_per_100g, protein_per_100g, fat_per_100g, carbs_per_100g, is_favorite, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    user_id, name.strip(), calories_per_100g,
                    protein_per_100g, fat_per_100g, carbs_per_100g,
                    1 if is_favorite else 0, datetime.utcnow().isoformat()
                )
            )
            await conn.commit()
            return cur.lastrowid

    async def get_custom_foods(self, user_id: int) -> List[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM custom_foods WHERE user_id = ? ORDER BY is_favorite DESC, name ASC;",
                (user_id,)
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def match_custom_food(self, user_id: int, query_name: str) -> Optional[Dict[str, Any]]:
        """Finds custom food with matching name to prioritize over Gemini estimation."""
        clean = query_name.strip().lower()
        foods = await self.get_custom_foods(user_id)
        for f in foods:
            f_name = f["name"].strip().lower()
            if f_name == clean or f_name in clean or clean in f_name:
                return f
        return None

    # --- Pantry Items ---

    async def add_pantry_item(self, user_id: int, name: str, amount_str: Optional[str] = None) -> int:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "INSERT INTO pantry_items (user_id, name, amount_str, created_at) VALUES (?, ?, ?, ?);",
                (user_id, name.strip(), amount_str, datetime.utcnow().isoformat())
            )
            await conn.commit()
            return cur.lastrowid

    async def get_pantry_items(self, user_id: int) -> List[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM pantry_items WHERE user_id = ? ORDER BY id DESC;",
                (user_id,)
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def delete_pantry_item(self, pantry_id: int, user_id: int) -> bool:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "DELETE FROM pantry_items WHERE id = ? AND user_id = ?;",
                (pantry_id, user_id)
            )
            await conn.commit()
            return cur.rowcount > 0

    async def deduct_pantry_items(self, user_id: int, consumed_names: List[str]) -> List[str]:
        """Automatically write off items from pantry when eaten."""
        deducted = []
        pantry = await self.get_pantry_items(user_id)
        for item in pantry:
            p_name = item["name"].lower()
            for c_name in consumed_names:
                if p_name in c_name.lower() or c_name.lower() in p_name:
                    await self.delete_pantry_item(item["id"], user_id)
                    deducted.append(item["name"])
                    break
        return deducted

    # --- Supplements ---

    async def get_supplements(self, user_id: int) -> List[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute("SELECT * FROM supplements WHERE user_id = ?;", (user_id,))
            rows = await cur.fetchall()
            if not rows:
                # Default supplements for bulking if empty
                await conn.execute(
                    "INSERT INTO supplements (user_id, name, dosage, schedule_time, created_at) VALUES (?, 'Креатин', '5 г', '09:00', ?);",
                    (user_id, datetime.utcnow().isoformat())
                )
                await conn.execute(
                    "INSERT INTO supplements (user_id, name, dosage, schedule_time, created_at) VALUES (?, 'Сывороточный протеин', '30 г', '16:00', ?);",
                    (user_id, datetime.utcnow().isoformat())
                )
                await conn.commit()
                cur = await conn.execute("SELECT * FROM supplements WHERE user_id = ?;", (user_id,))
                rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def log_supplements_taken(self, user_id: int, taken_date: str) -> None:
        supps = await self.get_supplements(user_id)
        async with self.db.get_connection() as conn:
            for s in supps:
                await conn.execute(
                    "INSERT INTO supplement_logs (supplement_id, user_id, taken_date, created_at) VALUES (?, ?, ?, ?);",
                    (s["id"], user_id, taken_date, datetime.utcnow().isoformat())
                )
            await conn.commit()
