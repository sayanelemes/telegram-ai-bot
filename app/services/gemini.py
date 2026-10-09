import asyncio
import json
import logging
import re
from typing import List, Optional
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class GeminiServiceError(Exception):
    """Custom exception for Gemini AI service errors."""
    pass


# --- Pydantic models for Gemini structured responses ---

class FoodItemAnalysis(BaseModel):
    name: str = Field(description="Название продукта или блюда на русском языке")
    portion_g: float = Field(description="Ориентировочный вес порции в граммах", ge=1.0)
    calories: int = Field(description="Калорийность порции в ккал", ge=0)
    protein_g: float = Field(description="Белки в граммах", ge=0.0)
    fat_g: float = Field(description="Жиры в граммах", ge=0.0)
    carbs_g: float = Field(description="Углеводы в граммах", ge=0.0)


class FoodAnalysisResult(BaseModel):
    meal_name: str = Field(description="Общее название блюда или приёма пищи", default="Блюдо")
    items: List[FoodItemAnalysis] = Field(description="Список распознанных продуктов")
    total_calories: int = Field(description="Суммарные калории", ge=0)
    total_protein: float = Field(description="Суммарные белки в граммах", ge=0.0)
    total_fat: float = Field(description="Суммарные жиры в граммах", ge=0.0)
    total_carbs: float = Field(description="Суммарные углеводы в граммах", ge=0.0)
    advice: Optional[str] = Field(
        default=None,
        description="Краткий дружелюбный совет по балансу нутриентов (без медицинских диагнозов)"
    )


class ReceiptItemAnalysis(BaseModel):
    name: str = Field(description="Название товара")
    price: float = Field(description="Стоимость товара за указанное количество", ge=0.0)
    quantity: float = Field(default=1.0, description="Количество", ge=0.01)


class ReceiptAnalysisResult(BaseModel):
    merchant: str = Field(description="Название магазина, супермаркета или заведения", default="Магазин")
    date: Optional[str] = Field(default=None, description="Дата покупки (ГГГГ-ММ-ДД если видно)")
    currency: str = Field(default="₸", description="Символ или код валюты (например ₸, ₽, $)")
    category: str = Field(
        default="food",
        description="Категория: food, transport, shopping, entertainment, utilities, other"
    )
    entry_type: str = Field(default="expense", description="'expense' или 'income'")
    is_impulsive: bool = Field(default=False, description="Является ли покупка импульсивной/спонтанной")
    ai_analysis: Optional[str] = Field(default=None, description="Краткий AI-вердикт и финансовая рекомендация")
    items: List[ReceiptItemAnalysis] = Field(default_factory=list, description="Позиции в чеке")
    total_amount: float = Field(description="Итоговая сумма чека", ge=0.0)


class ExpenseParsedResult(BaseModel):
    merchant: str = Field(description="Название места, источника или получателя", default="Операция")
    amount: float = Field(description="Сумма операции", ge=0.0)
    currency: str = Field(default="₸", description="Валюта (например ₸, ₽, $)")
    category: str = Field(
        default="food",
        description="Категория: food, transport, shopping, entertainment, utilities, salary, business, gift, investments, other"
    )
    entry_type: str = Field(default="expense", description="'expense' (расход) или 'income' (доход)")
    is_impulsive: bool = Field(default=False, description="Является ли трата импульсивной (сладости, фастфуд, спонтанные вещи)")
    ai_analysis: Optional[str] = Field(default=None, description="Вердикт AI: '⚠️ Импульсивная покупка! Не рекомендуется' или '✅ Необходимая трата' с кратким советом")
    description: Optional[str] = Field(default=None, description="Описание операции")
    items: List[ReceiptItemAnalysis] = Field(default_factory=list, description="Список товаров")


# --- Gemini Service Implementation ---

class GeminiService:
    def __init__(self, api_key: str, model_name: str = "gemini-3.5-flash"):
        self.api_key = api_key
        self.model_name = model_name
        self._client: Optional[genai.Client] = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            if not self.api_key:
                raise GeminiServiceError("GEMINI_API_KEY не задан в конфигурации.")
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    @staticmethod
    def _extract_json_text(text: str) -> str:
        """Strip markdown code block fences if Gemini wraps JSON in ```json."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text

    async def _generate_with_fallback(
        self,
        contents: list,
        config: types.GenerateContentConfig,
        timeout_seconds: float = 14.0
    ):
        """
        Fast execution: disables extended thinking (thinking_budget=0),
        enforces a timeout, and falls back to alternate fast models if 503 or hang occurs.
        """
        if config.thinking_config is None:
            config.thinking_config = types.ThinkingConfig(thinking_budget=0)

        candidate_models = [self.model_name]
        for fallback in ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-flash-latest"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        last_error = None
        for model in candidate_models:
            try:
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=model,
                        contents=contents,
                        config=config,
                    ),
                    timeout=timeout_seconds
                )
                return response
            except Exception as e:
                logger.warning(f"Model '{model}' timed out or failed: {e}. Trying fallback...")
                last_error = e

        raise GeminiServiceError(f"Ошибка вызова Gemini AI: {last_error}")

    async def analyze_food(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg"
    ) -> FoodAnalysisResult:
        """
        Analyze a food photo using Gemini vision.
        Returns parsed products, weights, calories, and macronutrients.
        """
        prompt = (
            "Ты — опытный нутрициолог. Внимательно проанализируй эту фотографию еды.\n"
            "1. Распознай каждое блюдо и ингредиент на тарелке.\n"
            "2. Оцени примерный вес порции каждого ингредиента в граммах.\n"
            "3. Рассчитай калории (ккал), белки (г), жиры (г), углеводы (г) для каждого продукта.\n"
            "4. Посчитай суммарные итоги (total_calories, total_protein, total_fat, total_carbs).\n"
            "5. Добавь короткий (1-2 предложения) практический и полезный совет по нутриентам. "
            "ВАЖНО: Никаких медицинских диагнозов и врачебных назначений!\n"
            "Все названия пиши на чистом русском языке."
        )

        try:
            image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=FoodAnalysisResult,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                temperature=0.2,
            )

            response = await self._generate_with_fallback(
                contents=[image_part, prompt],
                config=config,
                timeout_seconds=14.0
            )

            raw_text = self._extract_json_text(response.text or "")
            if not raw_text:
                raise GeminiServiceError("Пустой ответ от модели.")

            result = FoodAnalysisResult.model_validate_json(raw_text)

            # Sanity checks and recalibration
            calc_cals = sum(item.calories for item in result.items)
            if abs(result.total_calories - calc_cals) > 20:
                result.total_calories = calc_cals
            result.total_protein = round(sum(item.protein_g for item in result.items), 1)
            result.total_fat = round(sum(item.fat_g for item in result.items), 1)
            result.total_carbs = round(sum(item.carbs_g for item in result.items), 1)

            return result

        except Exception as e:
            logger.error(f"Gemini analyze_food error: {e}", exc_info=True)
            raise GeminiServiceError(f"Ошибка анализа еды с помощью AI: {e}")

    async def analyze_food_text(self, text: str) -> FoodAnalysisResult:
        """
        Analyze textual food description (e.g. 'Овсянка 200г с бананом и кофе').
        """
        prompt = (
            f"Пользователь описал свой приём пищи текстом:\n\"{text}\"\n\n"
            "1. Определи продукты и примерный размер порций.\n"
            "2. Рассчитай калории, белки, жиры и углеводы.\n"
            "3. Посчитай суммарные итоги.\n"
            "4. Добавь короткий полезный комментарий без медицинских диагнозов.\n"
            "Все названия пиши на русском языке."
        )

        try:
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=FoodAnalysisResult,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                temperature=0.2,
            )

            response = await self._generate_with_fallback(
                contents=[prompt],
                config=config,
                timeout_seconds=12.0
            )

            raw_text = self._extract_json_text(response.text or "")
            result = FoodAnalysisResult.model_validate_json(raw_text)

            calc_cals = sum(item.calories for item in result.items)
            if abs(result.total_calories - calc_cals) > 20:
                result.total_calories = calc_cals
            result.total_protein = round(sum(item.protein_g for item in result.items), 1)
            result.total_fat = round(sum(item.fat_g for item in result.items), 1)
            result.total_carbs = round(sum(item.carbs_g for item in result.items), 1)

            return result
        except Exception as e:
            logger.error(f"Gemini analyze_food_text error: {e}", exc_info=True)
            raise GeminiServiceError(f"Ошибка распознавания описания блюда: {e}")

    async def analyze_receipt(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg"
    ) -> ReceiptAnalysisResult:
        """
        Analyze a store receipt photo using Gemini vision.
        Extracts merchant name, purchase date, total, currency, items, and expense category.
        """
        prompt = (
            "Ты — умный финансовый консультант. Проанализируй фотографию кассового чека.\n"
            "1. Определи название магазина / заведения (merchant).\n"
            "2. Определи дату чека в формате ГГГГ-ММ-ДД (если видна).\n"
            "3. Определи валюту (по умолчанию '₸', если Казахстан/тг; или '₽', '$').\n"
            "4. Извлеки основные товары и их цены.\n"
            "5. Определи итоговую сумму чека (total_amount).\n"
            "6. Определи категорию расхода (food, transport, shopping, entertainment, utilities, other).\n"
            "7. Оцени, является ли чек импульсивной/спонтанной тратой (фастфуд, чипсы, сладости, алкоголь, спонтанные вещи).\n"
            "   - Заполни is_impulsive: true или false.\n"
            "   - В ai_analysis дай оценку, например: '⚠️ Импульсивная покупка! Не рекомендуется для бюджета.' или '✅ Базовые необходимые продукты.' плюс 1 короткий совет.\n"
            "Все названия на русском языке."
        )

        try:
            image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ReceiptAnalysisResult,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                temperature=0.1,
            )

            response = await self._generate_with_fallback(
                contents=[image_part, prompt],
                config=config,
                timeout_seconds=14.0
            )

            raw_text = self._extract_json_text(response.text or "")
            result = ReceiptAnalysisResult.model_validate_json(raw_text)

            # If total_amount is 0 but items have prices, calculate total
            if result.total_amount <= 0.0 and result.items:
                result.total_amount = sum(it.price for it in result.items)

            return result

        except Exception as e:
            logger.error(f"Gemini analyze_receipt error: {e}", exc_info=True)
            raise GeminiServiceError(f"Ошибка распознавания чека: {e}")

    async def parse_expense(self, text: str) -> ExpenseParsedResult:
        """
        Parse text expense like 'кофе 1200 тг' or 'потратил 8500 тг в Magnum'.
        """
        prompt = (
            f"Пользователь записал финансовую операцию (расход или доход) следующим текстом:\n\"{text}\"\n\n"
            "Извлеки из текста:\n"
            "- merchant (название магазина, сервиса, источника дохода или суть операции)\n"
            "- amount (числовая сумма)\n"
            "- currency (валюта, например '₸' для тг/тенге, '₽' для руб, '$' для usd)\n"
            "- entry_type ('income' если получены деньги, зарплата, перевод; иначе 'expense')\n"
            "- category (если доход: salary, business, gift, investments, other_income; если расход: food, transport, shopping, entertainment, utilities, other)\n"
            "- is_impulsive (true если это спонтанная/эмоциональная трата на фастфуд, сладости, развлечения, импульсивные покупки; иначе false)\n"
            "- ai_analysis (если доход: '💰 Доход зафиксирован'; если импульсивная трата: '⚠️ Импульсивная покупка! Не рекомендуется для бюджета.' + 1 совет; если базовая: '✅ Необходимый плановый расход.')\n"
            "- description (подробности или то, что купил)\n"
            "- items (список позиций если перечислено несколько)\n"
            "Ответь строго в формате JSON."
        )

        try:
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ExpenseParsedResult,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                temperature=0.1,
            )

            response = await self._generate_with_fallback(
                contents=[prompt],
                config=config,
                timeout_seconds=12.0
            )

            raw_text = self._extract_json_text(response.text or "")
            result = ExpenseParsedResult.model_validate_json(raw_text)
            return result

        except Exception as e:
            logger.error(f"Gemini parse_expense error: {e}", exc_info=True)
            raise GeminiServiceError(f"Ошибка распознавания расхода из текста: {e}")

    async def generate_food_advice(
        self,
        consumed_calories: int,
        target_calories: int,
        consumed_protein: float,
        target_protein: int,
        consumed_fat: float,
        target_fat: int,
        consumed_carbs: float,
        target_carbs: int,
        new_food_name: str
    ) -> str:
        """
        Generate short, non-medical nutrition insight based on today's progress.
        """
        prompt = (
            f"Пользователь только что добавил в дневник: {new_food_name}.\n"
            f"Текущие показатели за день:\n"
            f"- Калории: {consumed_calories} из {target_calories} ккал\n"
            f"- Белки: {consumed_protein:.1f} из {target_protein} г\n"
            f"- Жиры: {consumed_fat:.1f} из {target_fat} г\n"
            f"- Углеводы: {consumed_carbs:.1f} из {target_carbs} г\n\n"
            "Дай краткий (2-3 предложения), ободряющий и практичный совет по питанию на оставшуюся часть дня. "
            "Например, если белка уже достаточно, посоветуй сфокусироваться на овощах или клетчатке. "
            "ВАЖНО: Не ставь медицинских диагнозов и не давай врачебных предписаний."
        )

        try:
            config = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                temperature=0.7,
            )
            response = await self._generate_with_fallback(
                contents=[prompt],
                config=config,
                timeout_seconds=10.0
            )
            return (response.text or "").strip()
        except Exception as e:
            logger.warning(f"Could not generate food advice: {e}")
            return "Приятного аппетита! Продолжайте следить за балансом калорий и макронутриентов."
