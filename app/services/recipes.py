import json
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo

from app.config.settings import settings
from app.database.connection import DatabaseManager
from app.database.models import FoodEntryDB, FoodItemDB, ExpenseDB, ExpenseItemDB
from app.database.repositories.user_repository import UserRepository
from app.database.repositories.food_repository import FoodRepository
from app.database.repositories.expense_repository import ExpenseRepository
from app.services.gemini import (
    GeminiService,
    RecipeGenerated,
    WeeklyMealPlanResult,
    GeminiServiceError,
)

logger = logging.getLogger(__name__)


class RecipeService:
    def __init__(
        self,
        db_manager: DatabaseManager,
        user_repo: UserRepository,
        food_repo: FoodRepository,
        expense_repo: ExpenseRepository,
        gemini_service: GeminiService,
    ):
        self.db = db_manager
        self.user_repo = user_repo
        self.food_repo = food_repo
        self.expense_repo = expense_repo
        self.gemini_service = gemini_service

    async def get_price_hints(self, user_id: int) -> str:
        """
        Extract user's actual food expense history to provide real-world price hints.
        Includes Kazakhstan defaults for bulking essentials.
        """
        defaults = [
            "Яйца (10 шт): 650 ₸",
            "Творог 5% (400 г): 600 ₸",
            "Молоко 3.2% (1 л): 450 ₸",
            "Овсяные хлопья (500 г): 450 ₸",
            "Бананы (1 кг): 850 ₸",
            "Арахисовая паста (300 г): 1200 ₸",
            "Куриное филе (1 кг): 2200 ₸",
            "Грудка индейки (1 кг): 3200 ₸",
            "Рис круглозерный (800 г): 550 ₸",
            "Гречка (800 г): 480 ₸",
            "Макароны твердых сортов (400 г): 380 ₸",
        ]

        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT name, price FROM expense_items ei "
                "JOIN expenses e ON ei.expense_id = e.id "
                "WHERE e.user_id = ? AND e.category = 'food' "
                "ORDER BY e.expense_date DESC LIMIT 15;",
                (user_id,)
            )
            rows = await cur.fetchall()

        custom_hints = []
        for r in rows:
            custom_hints.append(f"{r['name']}: {float(r['price']):.0f} ₸")

        combined = custom_hints + defaults
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for h in combined:
            k = h.split(":")[0].strip().lower()
            if k not in seen:
                seen.add(k)
                unique.append(f"- {h}")

        return "\n".join(unique[:12])

    async def suggest_recipe(
        self,
        user_id: int,
        mode: str = "remaining",
        custom_calories: Optional[int] = None,
        custom_protein: Optional[float] = None,
        custom_fat: Optional[float] = None,
        custom_carbs: Optional[float] = None,
        preferences: Optional[str] = None,
        timezone_str: str = "Asia/Almaty",
    ) -> Dict[str, Any]:
        """
        Suggest a recipe tailored to bulking goals:
        - mode 'remaining': uses remaining calories/macros of the day.
        - mode 'custom': uses specified targets.
        """
        try:
            tz = ZoneInfo(timezone_str)
        except Exception:
            tz = ZoneInfo("Asia/Almaty")
        today_str = datetime.now(tz).strftime("%Y-%m-%d")

        if mode == "remaining":
            goal = await self.user_repo.get_calorie_goal(user_id)
            target_cal = goal.target_calories if goal else 2800
            target_p = goal.target_protein_g if goal else 150
            target_f = goal.target_fat_g if goal else 80
            target_c = goal.target_carbs_g if goal else 350

            daily = await self.food_repo.get_daily_totals(user_id, today_str)
            rem_cal = target_cal - daily["calories"]
            rem_p = target_p - daily["protein"]
            rem_f = target_f - daily["fat"]
            rem_c = target_c - daily["carbs"]

            # Set sensible floors for a single meal
            calc_calories = max(300, rem_cal)
            calc_protein = max(20.0, rem_p)
            calc_fat = max(10.0, rem_f)
            calc_carbs = max(35.0, rem_c)
        else:
            calc_calories = custom_calories or 600
            calc_protein = custom_protein or 35.0
            calc_fat = custom_fat or 20.0
            calc_carbs = custom_carbs or 70.0

        price_hints = await self.get_price_hints(user_id)

        recipe = await self.gemini_service.generate_recipe(
            target_calories=calc_calories,
            target_protein=calc_protein,
            target_fat=calc_fat,
            target_carbs=calc_carbs,
            price_hints=price_hints,
            max_cost=settings.MAX_MEAL_COST,
            preferences=preferences,
            user_id=user_id,
        )

        recipe_dict = recipe.model_dump()
        link_id = f"recipe_{uuid.uuid4().hex[:10]}"
        recipe_dict["link_id"] = link_id
        recipe_dict["mode"] = mode

        # Cache in last_recipes table with 24-hour TTL
        now_ts = int(time.time())
        async with self.db.get_connection() as conn:
            await conn.execute(
                "INSERT INTO last_recipes (user_id, recipe_json, created_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "recipe_json = excluded.recipe_json, "
                "created_at = excluded.created_at;",
                (user_id, json.dumps(recipe_dict, ensure_ascii=False), now_ts)
            )
            await conn.commit()

        return recipe_dict

    async def get_last_recipe(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Fetch last generated recipe if within 24-hour TTL."""
        now_ts = int(time.time())
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT recipe_json, created_at FROM last_recipes WHERE user_id = ?;",
                (user_id,)
            )
            row = await cur.fetchone()
            if not row:
                return None

            created_at = row["created_at"]
            if (now_ts - created_at) > 86400:  # 24 hours TTL
                await conn.execute("DELETE FROM last_recipes WHERE user_id = ?;", (user_id,))
                await conn.commit()
                return None

            return json.loads(row["recipe_json"])

    async def quick_log_meal(
        self,
        user_id: int,
        request_id: str,
        recipe_data: Optional[Dict[str, Any]] = None,
        meal_type: str = "meal",
        timezone_str: str = "Asia/Almaty",
    ) -> Dict[str, Any]:
        """
        Quick-log an eaten recipe meal with idempotency protection against double taps.
        TTL for idempotency key is 10 minutes (600s).
        """
        now_ts = int(time.time())

        async with self.db.get_connection() as conn:
            # 1. Clean expired idempotency keys
            await conn.execute("DELETE FROM idempotency_keys WHERE expires_at < ?;", (now_ts,))

            # 2. Check for active idempotency key
            cur = await conn.execute(
                "SELECT response_json FROM idempotency_keys WHERE key = ? AND user_id = ?;",
                (request_id, user_id)
            )
            existing = await cur.fetchone()
            if existing:
                logger.info(f"Duplicate quick-log request {request_id} intercepted by idempotency key.")
                return json.loads(existing["response_json"])

        # 3. Determine recipe
        if not recipe_data:
            recipe_data = await self.get_last_recipe(user_id)
        if not recipe_data:
            raise ValueError("Нет активного рецепта для записи.")

        try:
            tz = ZoneInfo(timezone_str)
        except Exception:
            tz = ZoneInfo("Asia/Almaty")
        now_dt = datetime.now(tz)
        today_str = now_dt.strftime("%Y-%m-%d")
        time_str = now_dt.strftime("%H:%M")

        link_id = recipe_data.get("link_id") or f"quick_{uuid.uuid4().hex[:10]}"
        recipe_name = recipe_data.get("name", "Блюдо по рецепту")
        calories = int(recipe_data.get("calories", 0))
        protein = float(recipe_data.get("protein_g", 0.0))
        fat = float(recipe_data.get("fat_g", 0.0))
        carbs = float(recipe_data.get("carbs_g", 0.0))

        # Build items
        items = []
        raw_ingredients = recipe_data.get("ingredients", [])
        for ing in raw_ingredients:
            items.append(FoodItemDB(
                name=ing.get("name", "Ингредиент"),
                portion_g=float(ing.get("grams", 100.0)),
                calories=int(calories / max(1, len(raw_ingredients))),
                protein_g=round(protein / max(1, len(raw_ingredients)), 1),
                fat_g=round(fat / max(1, len(raw_ingredients)), 1),
                carbs_g=round(carbs / max(1, len(raw_ingredients)), 1),
            ))

        if not items:
            items = [FoodItemDB(
                name=recipe_name,
                portion_g=350.0,
                calories=calories,
                protein_g=protein,
                fat_g=fat,
                carbs_g=carbs,
            )]

        food_entry = FoodEntryDB(
            user_id=user_id,
            meal_type=meal_type,
            entry_date=today_str,
            entry_time=time_str,
            total_calories=calories,
            total_protein=protein,
            total_fat=fat,
            total_carbs=carbs,
            advice=recipe_data.get("high_calorie_bulking_tip") or "Отличный приём пищи для профицита калорий!",
            items=items,
        )

        saved = await self.food_repo.create_food_entry(food_entry)

        # 4. Auto-deduct from pantry if matching ingredients exist
        consumed_names = [it.name for it in items]
        deducted = await self.food_repo.deduct_pantry_items(user_id, consumed_names)

        response_data = {
            "success": True,
            "entry_id": saved.id,
            "meal_type": saved.meal_type,
            "calories": saved.total_calories,
            "protein": saved.total_protein,
            "fat": saved.total_fat,
            "carbs": saved.total_carbs,
            "deducted_from_pantry": deducted,
            "message": f"✅ Рецепт '{recipe_name}' записан в съеденное (+{calories} ккал)!",
        }

        # 5. Store in idempotency_keys with 10 minutes TTL
        expires_at = now_ts + 600
        async with self.db.get_connection() as conn:
            await conn.execute(
                "INSERT INTO idempotency_keys (key, user_id, response_json, expires_at) "
                "VALUES (?, ?, ?, ?);",
                (request_id, user_id, json.dumps(response_data, ensure_ascii=False), expires_at)
            )
            await conn.commit()

        return response_data

    async def save_recipe_to_expenses(
        self,
        user_id: int,
        recipe_data: Optional[Dict[str, Any]] = None,
        custom_cost: Optional[float] = None,
        timezone_str: str = "Asia/Almaty",
    ) -> Dict[str, Any]:
        """
        Record recipe ingredients directly into expenses with source='recipe'.
        """
        if not recipe_data:
            recipe_data = await self.get_last_recipe(user_id)
        if not recipe_data:
            raise ValueError("Нет активного рецепта для записи в расходы.")

        try:
            tz = ZoneInfo(timezone_str)
        except Exception:
            tz = ZoneInfo("Asia/Almaty")
        today_str = datetime.now(tz).strftime("%Y-%m-%d")

        recipe_name = recipe_data.get("name", "Рецепт")
        cost = custom_cost if custom_cost is not None else float(recipe_data.get("estimated_cost", 1000.0))

        items_db = []
        for ing in recipe_data.get("ingredients", []):
            items_db.append(ExpenseItemDB(
                name=ing.get("name", "Продукт"),
                price=float(ing.get("estimated_price", cost / max(1, len(recipe_data.get("ingredients", []))))),
                quantity=1.0,
            ))

        expense = ExpenseDB(
            user_id=user_id,
            merchant=f"Продукты под рецепт: {recipe_name}",
            amount=cost,
            currency="₸",
            category="food",
            entry_type="expense",
            is_impulsive=False,
            source="recipe",
            description=f"Ингредиенты для: {recipe_name}",
            expense_date=today_str,
            items=items_db,
        )

        saved = await self.expense_repo.create_expense(expense)
        return {
            "success": True,
            "expense_id": saved.id,
            "amount": saved.amount,
            "merchant": saved.merchant,
            "message": f"💰 Расход {saved.amount:,.0f} ₸ добавлен под рецепт '{recipe_name}'",
        }

    # --- Shopping List Methods ---

    async def get_shopping_items(self, user_id: int) -> List[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT id, user_id, name, amount_str, category, is_bought, bought_price, created_at "
                "FROM shopping_items WHERE user_id = ? ORDER BY is_bought ASC, id DESC;",
                (user_id,)
            )
            rows = await cur.fetchall()
            return [
                {
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "name": r["name"],
                    "amount_str": r["amount_str"],
                    "category": r["category"],
                    "is_bought": bool(r["is_bought"]),
                    "bought_price": r["bought_price"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]

    async def add_shopping_item(
        self,
        user_id: int,
        name: str,
        amount_str: Optional[str] = None,
        category: str = "food",
    ) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "INSERT INTO shopping_items (user_id, name, amount_str, category, is_bought, created_at) "
                "VALUES (?, ?, ?, ?, 0, ?);",
                (user_id, name.strip(), amount_str, category, now)
            )
            item_id = cur.lastrowid
            await conn.commit()

        return {
            "id": item_id,
            "user_id": user_id,
            "name": name.strip(),
            "amount_str": amount_str,
            "category": category,
            "is_bought": False,
            "created_at": now,
        }

    async def toggle_shopping_item(
        self,
        user_id: int,
        item_id: int,
        is_bought: Optional[bool] = None,
        bought_price: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT is_bought FROM shopping_items WHERE id = ? AND user_id = ?;",
                (item_id, user_id)
            )
            row = await cur.fetchone()
            if not row:
                return None

            curr_val = bool(row["is_bought"])
            new_val = (not curr_val) if is_bought is None else bool(is_bought)
            val_int = 1 if new_val else 0

            await conn.execute(
                "UPDATE shopping_items SET is_bought = ?, bought_price = ? WHERE id = ? AND user_id = ?;",
                (val_int, bought_price, item_id, user_id)
            )
            await conn.commit()

            cur2 = await conn.execute(
                "SELECT * FROM shopping_items WHERE id = ? AND user_id = ?;",
                (item_id, user_id)
            )
            res = await cur2.fetchone()
            d = dict(res)
            d["is_bought"] = bool(d["is_bought"])
            return d

    async def delete_shopping_item(self, user_id: int, item_id: int) -> bool:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "DELETE FROM shopping_items WHERE id = ? AND user_id = ?;",
                (item_id, user_id)
            )
            await conn.commit()
            return cur.rowcount > 0

    async def clear_bought_items(self, user_id: int) -> int:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "DELETE FROM shopping_items WHERE user_id = ? AND is_bought = 1;",
                (user_id,)
            )
            await conn.commit()
            return cur.rowcount

    async def add_recipe_to_shopping_list(
        self,
        user_id: int,
        recipe_data: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Add all ingredients from a recipe to the shopping list with one tap."""
        if not recipe_data:
            recipe_data = await self.get_last_recipe(user_id)
        if not recipe_data:
            raise ValueError("Рецепт не найден.")

        added = []
        for ing in recipe_data.get("ingredients", []):
            item = await self.add_shopping_item(
                user_id=user_id,
                name=ing.get("name", "Продукт"),
                amount_str=ing.get("amount"),
                category="food",
            )
            added.append(item)
        return added

    # --- Weekly Meal Plan ---

    async def generate_weekly_meal_plan(
        self,
        user_id: int,
        preferences: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate and persist a 7-day bulking plan and aisle-grouped shopping list."""
        goal = await self.user_repo.get_calorie_goal(user_id)
        target_cal = goal.target_calories if goal else 2800
        target_p = goal.target_protein_g if goal else 150
        target_f = goal.target_fat_g if goal else 80
        target_c = goal.target_carbs_g if goal else 350

        plan = await self.gemini_service.generate_weekly_plan(
            daily_target_calories=target_cal,
            daily_target_protein=target_p,
            daily_target_fat=target_f,
            daily_target_carbs=target_c,
            preferences=preferences,
            user_id=user_id,
        )

        plan_dict = plan.model_dump()
        today_str = datetime.utcnow().strftime("%Y-%m-%d")

        async with self.db.get_connection() as conn:
            await conn.execute(
                "INSERT INTO weekly_meal_plans (user_id, plan_json, week_start_date, created_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "plan_json = excluded.plan_json, "
                "week_start_date = excluded.week_start_date, "
                "created_at = excluded.created_at;",
                (user_id, json.dumps(plan_dict, ensure_ascii=False), today_str, datetime.utcnow().isoformat())
            )
            await conn.commit()

        return plan_dict

    async def get_weekly_meal_plan(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT plan_json, week_start_date FROM weekly_meal_plans WHERE user_id = ?;",
                (user_id,)
            )
            row = await cur.fetchone()
            if not row:
                return None
            data = json.loads(row["plan_json"])
            data["week_start_date"] = row["week_start_date"]
            return data

    async def import_weekly_plan_to_shopping_list(self, user_id: int) -> int:
        """Import all items from weekly shopping list into user's shopping checklist."""
        plan_data = await self.get_weekly_meal_plan(user_id)
        if not plan_data:
            raise ValueError("Недельный план питания ещё не создан.")

        count = 0
        for group in plan_data.get("weekly_shopping_list", []):
            cat = group.get("aisle_name", "food")
            for item_name in group.get("items", []):
                await self.add_shopping_item(
                    user_id=user_id,
                    name=item_name,
                    category=cat,
                )
                count += 1
        return count
