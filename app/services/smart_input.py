import re
import uuid
import logging
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
from zoneinfo import ZoneInfo
from pydantic import BaseModel, Field
from google.genai import types

from app.config.settings import settings
from app.services.gemini import GeminiService, GeminiServiceError
from app.database.connection import DatabaseManager
from app.utils.formatters import format_currency, format_number

logger = logging.getLogger(__name__)


class SmartInputItem(BaseModel):
    name: str = Field(description="Название позиции")
    grams: Optional[float] = Field(default=None, description="Вес порции в граммах (null для не-еды)")
    calories: Optional[int] = Field(default=None, description="Калории (null для не-еды)")
    protein_g: Optional[float] = Field(default=None, description="Белки в граммах")
    fat_g: Optional[float] = Field(default=None, description="Жиры в граммах")
    carbs_g: Optional[float] = Field(default=None, description="Углеводы в граммах")
    price: Optional[float] = Field(default=None, description="Цена позиции (null если не указана)")
    category: Optional[str] = Field(default="food", description="Категория расхода")
    is_impulse: bool = Field(default=False, description="Является ли спонтанной/импульсивной покупкой")
    impulse_reason: Optional[str] = Field(default=None, description="Причина импульсивности")
    eaten_now: bool = Field(default=True, description="Съедено сразу на месте")


class SmartInputResult(BaseModel):
    intent: str = Field(
        description="Определённое намерение: food_and_expense | food_only | expense_only | recipe_request | recipe_to_budget | task | note | reminder | workout_log | workout_plan_request | other"
    )
    confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="Уверенность в распознавании")
    currency: str = Field(default="₸", description="Валюта операции")
    occurred_at: Optional[str] = Field(default=None, description="Время когда произошло (вчера, утром и т.д.)")
    clarification_needed: Optional[str] = Field(default=None, description="Вопрос для уточнения если есть сомнения")
    items: List[SmartInputItem] = Field(default_factory=list, description="Список распознанных элементов")
    summary_text: Optional[str] = Field(default=None, description="Краткое описание для пользователя")


class ProcessedInputOutcome(BaseModel):
    action: str  # 'saved', 'preview', 'ignored', 'fast_path'
    intent: str
    link_id: Optional[str] = None
    message: str
    confidence: float
    items: List[SmartInputItem] = Field(default_factory=list)
    food_entry_id: Optional[int] = None
    expense_id: Optional[int] = None
    water_ml: Optional[int] = None
    weight_kg: Optional[float] = None
    raw_result: Optional[SmartInputResult] = None


class SmartInputService:
    def __init__(self, db_manager: DatabaseManager, gemini_service: GeminiService):
        self.db = db_manager
        self.gemini = gemini_service

    # --- Fast-path regex parsers (No Gemini call needed) ---

    @staticmethod
    def parse_water_fast_path(text: str) -> Optional[int]:
        """Recognizes quick water inputs: '+250', 'вода 500', 'выпил стакан', '+500 мл'."""
        clean = text.strip().lower()
        if clean in ("+250", "+250мл", "+250 мл", "стакан воды", "вода 250", "вода"):
            return 250
        if clean in ("+500", "+500мл", "+500 мл", "вода 500"):
            return 500

        # Pattern: +400 мл, выпил 300 мл воды, вода 400
        match = re.search(r"(?:выпил\s+)?(?:\+\s*)?(\d+)\s*(?:мл|ml)?\s*(?:воды|вода)?", clean)
        if match:
            val = int(match.group(1))
            # Sensible water bounds (50 ml - 3000 ml)
            if 50 <= val <= 3000 and ("вод" in clean or "+" in clean or "мл" in clean):
                return val

        # Pattern: 1.5 л воды, 2л
        match_liters = re.search(r"(\d+[.,]?\d*)\s*(?:л|l)\s*(?:воды)?", clean)
        if match_liters and ("вод" in clean or "л" in clean):
            try:
                liters = float(match_liters.group(1).replace(",", "."))
                if 0.2 <= liters <= 5.0:
                    return int(liters * 1000)
            except ValueError:
                pass
        return None

    @staticmethod
    def parse_weight_fast_path(text: str) -> Optional[float]:
        """Recognizes quick weight inputs: 'вес 78.4', 'вешу 80.5', '78.4 кг'."""
        clean = text.strip().lower()
        match = re.search(r"(?:вес\s*[:=]?\s*|вешу\s*)(\d+[.,]?\d*)\s*(?:кг)?", clean)
        if match:
            try:
                w = float(match.group(1).replace(",", "."))
                if 30.0 <= w <= 300.0:
                    return round(w, 2)
            except ValueError:
                pass

        # Standalone: "78.4 кг" or "82кг"
        match_kg = re.search(r"^(\d+[.,]?\d*)\s*кг$", clean)
        if match_kg:
            try:
                w = float(match_kg.group(1).replace(",", "."))
                if 30.0 <= w <= 300.0:
                    return round(w, 2)
            except ValueError:
                pass
        return None

    @staticmethod
    def normalize_price_tokens(text: str) -> str:
        """
        Expands shorthand multipliers: '1.5к' -> '1500', '12к' -> '12000', '400 тг' -> '400 тенге'.
        """
        def replace_k(m):
            num = float(m.group(1).replace(",", "."))
            return str(int(num * 1000))

        # 1.5к / 12к / 25k
        normalized = re.sub(r"(\d+[.,]?\d*)\s*[кk](?![а-яa-z])", replace_k, text, flags=re.IGNORECASE)
        return normalized

    async def parse_single_phrase(
        self,
        text: str,
        user_id: int,
        timezone_str: str = "Asia/Almaty"
    ) -> SmartInputResult:
        """
        Uses Gemini with structured response_schema to categorize and extract all items.
        User input is wrapped strictly in <user_message> tags.
        """
        clean_text = self.normalize_price_tokens(text)

        prompt = (
            "Ты — интеллектуальный ассистент по питанию и личным финансам для человека на наборе массы.\n"
            "Пользователь отправил следующее сообщение:\n"
            f"<user_message>\n{clean_text}\n</user_message>\n\n"
            "Твоя задача — извлечь намерение и данные СТРОГО по следующим правилам:\n\n"
            "1. ОПРЕДЕЛЕНИЕ INTENT:\n"
            "   - 'food_and_expense': Пользователь купил и СРАЗУ съел/выпил готовую еду/напиток на месте с указанием цены "
            "     (например: 'купил сникерс за 400 тенге', 'кофе 1200 и сэндвич 2500').\n"
            "   - 'food_only': Пользователь съел еду БЕЗ указания цены или дома (например: 'съел два яйца и бутерброд').\n"
            "   - 'expense_only': Чистый расход без калорий (например: 'такси 2500', 'наушники 12к') "
            "     ИЛИ покупка сырых продуктов 'на потом' (например: 'купил пачку риса и 1 кг курицы за 3500').\n"
            "   - 'recipe_request': Запрос рецепта (например: 'что приготовить', 'дай рецепт').\n"
            "   - 'recipe_to_budget': Команда добавить прошлый рецепт в расходы/бюджет.\n"
            "   - 'task': Задача (например: 'надо оплатить интернет', 'записаться к врачу').\n"
            "   - 'note': Заметка или мысль (например: 'заметка: купить витамин д').\n"
            "   - 'reminder': Напоминание со временем (например: 'напомни завтра в 18:00 позвонить тренеру').\n"
            "   - 'workout_log': Запись подхода/веса (например: 'жим 60x8x3', 'присед 80 на 5 по 5').\n"
            "   - 'workout_plan_request': Запрос составления тренировок (например: 'составь план тренировок').\n"
            "   - 'other': Приветствия, шум, бессмысленный текст ('привет', 'как дела', 'ок').\n\n"
            "2. ПРАВИЛА ДЛЯ ITEMS:\n"
            "   - Для не-еды (такси, наушники) calories, protein_g, fat_g, carbs_g, grams ДОЛЖНЫ БЫТЬ null. НЕ ПРИДУМЫВАЙ КАЛОРИИ ДЛЯ ВЕЩЕЙ И ТАКСИ!\n"
            "   - Для еды оценивай типичные граммы порции (сникерс ≈ 50 г, яйцо ≈ 55 г, бутерброд ≈ 100 г). "
            "     Если в тексте указан вес ('200г творога') — он строго приоритетнее!\n"
            "   - Если цена не указана пользователем — price = null. НЕ ВЫДУМЫВАЙ ЦЕНУ ЕСЛИ ЕЁ НЕТ!\n"
            "   - ИМПУЛЬСИВНЫЕ ПОКУПКИ (is_impulse): сладости, снеки, чипсы, батончики, кофе навынос, фастфуд, спонтанные гаджеты, доставка. "
            "     Базовые продукты (крупа, яйца, творог, курица), коммуналка, бензин, лекарства — НЕ импульсивные (false). "
            "     При сомнении — false.\n\n"
            "3. CONFIDENCE: 0.95 для явных данных, 0.65-0.75 если есть неоднозначность или продукты 'на потом'.\n"
            "Все названия на русском языке."
        )

        try:
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SmartInputResult,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                temperature=0.1,
            )

            response = await self.gemini._generate_with_fallback(
                contents=[prompt],
                config=config,
                timeout_seconds=12.0,
                user_id=user_id
            )

            raw_text = self.gemini._extract_json_text(response.text or "")
            result = SmartInputResult.model_validate_json(raw_text)
            return result

        except GeminiServiceError:
            raise
        except Exception as e:
            logger.error(f"Error parsing single phrase with Gemini: {e}", exc_info=True)
            raise GeminiServiceError(f"Не удалось распознать фразу: {e}")

    async def execute_input(
        self,
        text: str,
        user_id: int,
        timezone_str: str = "Asia/Almaty"
    ) -> ProcessedInputOutcome:
        """
        End-to-end execution of single-phrase input:
        1. Fast regex path check (water, weight).
        2. Gemini structured parse.
        3. Transactional save with shared link_id.
        4. Auto-save if confidence >= 0.8; preview otherwise.
        """
        # 1. Fast-path: Water
        water_val = self.parse_water_fast_path(text)
        if water_val is not None:
            tz = ZoneInfo(timezone_str)
            today_str = datetime.now(tz).strftime("%Y-%m-%d")
            async with self.db.get_connection() as conn:
                await conn.execute(
                    "INSERT INTO water_logs (user_id, amount_ml, log_date, created_at) VALUES (?, ?, ?, ?);",
                    (user_id, water_val, today_str, datetime.utcnow().isoformat())
                )
                await conn.commit()
            return ProcessedInputOutcome(
                action="fast_path",
                intent="water_log",
                message=f"💧 Записано: +{water_val} мл воды.",
                confidence=1.0,
                water_ml=water_val
            )

        # 2. Fast-path: Weight
        weight_val = self.parse_weight_fast_path(text)
        if weight_val is not None:
            tz = ZoneInfo(timezone_str)
            today_str = datetime.now(tz).strftime("%Y-%m-%d")
            async with self.db.get_connection() as conn:
                await conn.execute(
                    "INSERT INTO weight_logs (user_id, weight_kg, log_date, created_at) VALUES (?, ?, ?, ?);",
                    (user_id, weight_val, today_str, datetime.utcnow().isoformat())
                )
                # Check profile for target recalculation if weight shifted >= 2kg
                p_cur = await conn.execute("SELECT weight_kg FROM user_profiles WHERE user_id = ?;", (user_id,))
                p_row = await p_cur.fetchone()
                if p_row and abs(p_row["weight_kg"] - weight_val) >= 2.0:
                    await conn.execute(
                        "UPDATE user_profiles SET weight_kg = ?, updated_at = ? WHERE user_id = ?;",
                        (weight_val, datetime.utcnow().isoformat(), user_id)
                    )
                await conn.commit()

            return ProcessedInputOutcome(
                action="fast_path",
                intent="weight_log",
                message=f"⚖️ Вес зафиксирован: {weight_val} кг.",
                confidence=1.0,
                weight_kg=weight_val
            )

        # 3. Gemini Parse
        parsed = await self.parse_single_phrase(text, user_id=user_id, timezone_str=timezone_str)

        if parsed.intent == "other" or not parsed.items:
            return ProcessedInputOutcome(
                action="ignored",
                intent=parsed.intent,
                message="Ничего не записано. Напишите, что вы съели или потратили (например: 'кофе 1200' или '2 яйца').",
                confidence=parsed.confidence,
                raw_result=parsed
            )

        link_id = f"link_{uuid.uuid4().hex[:12]}"
        tz = ZoneInfo(timezone_str)
        now = datetime.now(tz)
        today_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M")

        # Check if confidence meets auto-save threshold (>= 0.8)
        if parsed.confidence < 0.8:
            return ProcessedInputOutcome(
                action="preview",
                intent=parsed.intent,
                link_id=link_id,
                message="Требуется подтверждение перед сохранением.",
                confidence=parsed.confidence,
                items=parsed.items,
                raw_result=parsed
            )

        # 4. Atomic Save in a single database transaction
        saved_food_id: Optional[int] = None
        saved_expense_id: Optional[int] = None

        food_items_to_save = [it for it in parsed.items if it.calories is not None or it.grams is not None]
        expense_items_to_save = [it for it in parsed.items if it.price is not None and it.price > 0]

        async with self.db.get_connection() as conn:
            # 4a. Save Food if present
            if parsed.intent in ("food_and_expense", "food_only") and food_items_to_save:
                tot_cals = sum(it.calories or 0 for it in food_items_to_save)
                tot_p = sum(it.protein_g or 0.0 for it in food_items_to_save)
                tot_f = sum(it.fat_g or 0.0 for it in food_items_to_save)
                tot_c = sum(it.carbs_g or 0.0 for it in food_items_to_save)
                meal_name = ", ".join(it.name for it in food_items_to_save[:2])

                cur = await conn.execute(
                    """
                    INSERT INTO food_entries (
                        user_id, meal_type, entry_date, entry_time,
                        total_calories, total_protein, total_fat, total_carbs,
                        advice, link_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        user_id, meal_name, today_str, time_str,
                        tot_cals, round(tot_p, 1), round(tot_f, 1), round(tot_c, 1),
                        parsed.summary_text, link_id, datetime.utcnow().isoformat()
                    )
                )
                saved_food_id = cur.lastrowid

                for it in food_items_to_save:
                    await conn.execute(
                        """
                        INSERT INTO food_items (
                            food_entry_id, name, portion_g, calories, protein_g, fat_g, carbs_g
                        ) VALUES (?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            saved_food_id, it.name, it.grams or 100.0,
                            it.calories or 0, it.protein_g or 0.0, it.fat_g or 0.0, it.carbs_g or 0.0
                        )
                    )

            # 4b. Save Expense if present
            if parsed.intent in ("food_and_expense", "expense_only") and expense_items_to_save:
                tot_amount = sum(it.price or 0.0 for it in expense_items_to_save)
                merchant = expense_items_to_save[0].name
                category = expense_items_to_save[0].category or "food"
                is_impulse_flag = any(it.is_impulse for it in expense_items_to_save)
                impulse_reasons = [it.impulse_reason for it in expense_items_to_save if it.impulse_reason]
                impulse_reason_str = "; ".join(impulse_reasons) if impulse_reasons else None

                cur = await conn.execute(
                    """
                    INSERT INTO expenses (
                        user_id, merchant, amount, currency, category, entry_type,
                        description, raw_text, is_impulsive, is_impulse, impulse_reason,
                        link_id, source, expense_date, created_at
                    ) VALUES (?, ?, ?, ?, ?, 'expense', ?, ?, ?, ?, ?, ?, 'smart_input', ?, ?);
                    """,
                    (
                        user_id, merchant, tot_amount, parsed.currency, category,
                        parsed.summary_text or merchant, text,
                        1 if is_impulse_flag else 0, 1 if is_impulse_flag else 0,
                        impulse_reason_str, link_id, today_str, datetime.utcnow().isoformat()
                    )
                )
                saved_expense_id = cur.lastrowid

                for it in expense_items_to_save:
                    await conn.execute(
                        """
                        INSERT INTO expense_items (expense_id, name, price, quantity)
                        VALUES (?, ?, ?, 1.0);
                        """,
                        (saved_expense_id, it.name, it.price or 0.0)
                    )

            # Check remaining calories to goal
            goal_cur = await conn.execute("SELECT target_calories FROM calorie_goals WHERE user_id = ?;", (user_id,))
            g_row = await goal_cur.fetchone()
            target_c = g_row["target_calories"] if g_row else 2200

            sum_cur = await conn.execute(
                "SELECT SUM(total_calories) as sum_cals FROM food_entries WHERE user_id = ? AND entry_date = ?;",
                (user_id, today_str)
            )
            s_row = await sum_cur.fetchone()
            total_today = s_row["sum_cals"] or 0
            rem_c = max(0, target_c - total_today)

            await conn.commit()

        # Build friendly response message
        parts = []
        if food_items_to_save:
            food_desc = ", ".join(f"{it.name} (~{int(it.grams or 0)} г, {it.calories or 0} ккал)" for it in food_items_to_save)
            parts.append(f"✅ {food_desc}")
        if expense_items_to_save:
            tot_exp = sum(it.price or 0.0 for it in expense_items_to_save)
            imp_tag = " · 🛍 импульсивная" if any(it.is_impulse for it in expense_items_to_save) else ""
            parts.append(f"💰 {format_currency(tot_exp, parsed.currency)}{imp_tag}")
        if rem_c > 0:
            parts.append(f"До нормы {format_number(rem_c)} ккал.")

        result_message = " · ".join(parts) if parts else "Запись сохранена."

        return ProcessedInputOutcome(
            action="saved",
            intent=parsed.intent,
            link_id=link_id,
            message=result_message,
            confidence=parsed.confidence,
            items=parsed.items,
            food_entry_id=saved_food_id,
            expense_id=saved_expense_id,
            raw_result=parsed
        )

    async def undo_by_link_id(self, link_id: str, user_id: int) -> bool:
        """
        Atomically removes both food entry and expense associated with link_id.
        Strictly isolated by user_id.
        """
        if not link_id:
            return False

        async with self.db.get_connection() as conn:
            # Delete food entry and cascade items
            await conn.execute(
                "DELETE FROM food_entries WHERE link_id = ? AND user_id = ?;",
                (link_id, user_id)
            )
            # Delete expense and cascade items
            await conn.execute(
                "DELETE FROM expenses WHERE link_id = ? AND user_id = ?;",
                (link_id, user_id)
            )
            await conn.commit()
            return True
