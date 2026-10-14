import json
import logging
import re
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from app.database.repositories.workout_repository import WorkoutRepository
from app.database.repositories.user_repository import UserRepository
from app.services.gemini import GeminiService

logger = logging.getLogger(__name__)


# =========================================================================
# SCHEMAS FOR GEMINI STRUCTURED OUTPUT
# =========================================================================

class PlanExerciseSchema(BaseModel):
    name: str = Field(..., description="Название упражнения")
    sets: int = Field(3, description="Количество подходов")
    reps: str = Field("8-10", description="Диапазон повторов")
    rest_sec: int = Field(90, description="Отдых в секундах")
    notes: Optional[str] = Field(None, description="Техника или фокус")


class PlanDaySchema(BaseModel):
    day_name: str = Field(..., description="Название тренировочного дня (например, День А: Грудь и Спина)")
    exercises: List[PlanExerciseSchema] = Field(default_factory=list)


class WorkoutPlanSchema(BaseModel):
    name: str = Field(..., description="Название программы (например, Гипертрофия 4 дня)")
    days_per_week: int = Field(4, description="Количество дней в неделю")
    description: Optional[str] = Field(None, description="Краткое описание акцентов")
    days: List[PlanDaySchema] = Field(default_factory=list)


class WorkoutParsedItem(BaseModel):
    exercise_name: str = Field(..., description="Название упражнения")
    weight_kg: float = Field(..., description="Рабочий вес в кг")
    reps: int = Field(..., description="Количество повторений")
    sets: int = Field(..., description="Количество подходов")
    rpe: Optional[float] = Field(None, description="RPE шкала нагрузки (1-10)")


class WorkoutParseSchema(BaseModel):
    items: List[WorkoutParsedItem] = Field(default_factory=list)


# =========================================================================
# WORKOUT SERVICE
# =========================================================================

class WorkoutService:
    def __init__(
        self,
        workout_repo: WorkoutRepository,
        user_repo: UserRepository,
        gemini_service: GeminiService,
    ):
        self.workout_repo = workout_repo
        self.user_repo = user_repo
        self.gemini_service = gemini_service

    # =========================================================================
    # FAST REGEX PARSER
    # =========================================================================

    def parse_workout_text_regex(self, text: str) -> List[Dict[str, Any]]:
        """
        Regex patterns:
        - "жим 60x8x3" / "жим 60х8х3"
        - "разводка 12.5x10x4 @8"
        - "присед 100 5х5"
        - "тяга 80 кг 6 повт 4 подх"
        """
        items = []
        # Split by comma, semicolon or newline
        chunks = re.split(r"[,;\n]+", text.strip())

        pattern1 = re.compile(
            r"^(?P<name>[a-zA-Zа-яА-ЯёЁ\s\-]+?)\s+(?P<weight>\d+(?:[\.,]\d+)?)\s*(?:кг)?\s*[xхXХ*]\s*(?P<reps>\d+)\s*[xхXХ*]\s*(?P<sets>\d+)(?:\s*@(?P<rpe>\d+(?:[\.,]\d+)?))?$",
            re.IGNORECASE
        )
        pattern2 = re.compile(
            r"^(?P<name>[a-zA-Zа-яА-ЯёЁ\s\-]+?)\s+(?P<weight>\d+(?:[\.,]\d+)?)\s*(?:кг)?\s+(?P<sets>\d+)\s*[xхXХ*]\s*(?P<reps>\d+)(?:\s*@(?P<rpe>\d+(?:[\.,]\d+)?))?$",
            re.IGNORECASE
        )

        for chunk in chunks:
            raw = chunk.strip()
            if not raw:
                continue

            m = pattern1.match(raw) or pattern2.match(raw)
            if m:
                gd = m.groupdict()
                name = gd["name"].strip()
                weight = float(gd["weight"].replace(",", "."))
                reps = int(gd["reps"])
                sets = int(gd["sets"])
                rpe = float(gd["rpe"].replace(",", ".")) if gd.get("rpe") else None
                items.append({
                    "exercise_name": name.capitalize(),
                    "weight_kg": weight,
                    "reps": reps,
                    "sets": sets,
                    "rpe": rpe,
                    "raw_text": raw,
                })

        return items

    async def parse_workout_text(self, text: str) -> List[Dict[str, Any]]:
        """Tries fast regex first; if empty, uses Gemini structured output."""
        items = self.parse_workout_text_regex(text)
        if items:
            return items

        prompt = (
            "Ты спортивный AI-тренер. Разбери свободный текст записи тренировки на отдельные упражнения.\n"
            "Формат: название упражнения, вес (кг), повторы, подходы, RPE (если указан).\n"
            f"<user_text>{text}</user_text>"
        )

        try:
            res: WorkoutParseSchema = await self.gemini_service.call_structured(
                prompt=prompt,
                response_schema=WorkoutParseSchema,
                timeout=12.0,
            )
            return [
                {
                    "exercise_name": it.exercise_name.capitalize(),
                    "weight_kg": float(it.weight_kg),
                    "reps": int(it.reps),
                    "sets": int(it.sets),
                    "rpe": float(it.rpe) if it.rpe is not None else None,
                    "raw_text": f"{it.exercise_name} {it.weight_kg}x{it.reps}x{it.sets}",
                }
                for it in res.items
            ]
        except Exception as e:
            logger.warning(f"Gemini workout parse fallback failed: {e}")
            return []

    # =========================================================================
    # WORKOUT LOGGING & BULKING TIE-IN
    # =========================================================================

    async def log_workout(
        self,
        user_id: int,
        text: str,
        workout_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Parses text, logs exercises, detects PRs, computes tonnage, and builds bulking nutrition reminder.
        """
        d_str = workout_date or datetime.utcnow().strftime("%Y-%m-%d")
        items = await self.parse_workout_text(text)

        if not items:
            return {
                "success": False,
                "error": "Не удалось распознать упражнения. Пример формата: 'жим 60x8x3, разводка 12х10х3'",
                "logged_items": [],
                "tonnage_kg": 0,
                "prs": [],
            }

        logged_items = []
        prs = []
        total_tonnage = 0.0

        for it in items:
            logged = await self.workout_repo.log_exercise(
                user_id=user_id,
                workout_date=d_str,
                exercise_name=it["exercise_name"],
                weight_kg=it["weight_kg"],
                reps=it["reps"],
                sets=it["sets"],
                rpe=it.get("rpe"),
                raw_text=it.get("raw_text"),
            )
            logged_items.append(logged)
            total_tonnage += logged["volume_kg"]
            if logged["is_pr"]:
                prs.append(logged)

        # Bulking nutrition boost: +10% target calories
        goal = await self.user_repo.get_calorie_goal(user_id)
        base_cals = goal.target_calories if goal else 2500
        boosted_cals = round(base_cals * 1.10)

        # Build notification message
        pr_lines = ""
        if prs:
            pr_lines = "🏆 <b>НОВЫЕ ЛИЧНЫЕ РЕКОРДЫ (PR)!</b>\n" + "\n".join(
                f"  🎉 <b>{p['exercise_name']}</b>: {p['weight_kg']} кг (было {p['prev_max_weight']} кг)!" for p in prs
            ) + "\n\n"

        reminder_text = (
            f"💪 <b>Отличная тренировка! Тоннаж: {total_tonnage:.0f} кг.</b>\n\n"
            f"{pr_lines}"
            "🥩 <b>Анаболическое окно открыто!</b>\n"
            "Для максимального мышечного синтеза в течение часа прими 30-40 г белка и быстрыми углеводами:\n"
            "• Высокобелковый шейк (протеин + банан + молоко)\n"
            "• Творог с бананом и мёдом\n\n"
            f"🎯 <i>Норма калорий на сегодня увеличена на +10% (до {boosted_cals} ккал) для компенсации энергозатрат!</i>"
        )

        return {
            "success": True,
            "workout_date": d_str,
            "logged_items": logged_items,
            "tonnage_kg": round(total_tonnage, 1),
            "prs_count": len(prs),
            "prs": prs,
            "boosted_calories": boosted_cals,
            "reminder_message": reminder_text,
        }

    # =========================================================================
    # PLAN GENERATION & MODIFICATION
    # =========================================================================

    async def generate_plan(
        self,
        user_id: int,
        goal: str = "набор массы (гипертрофия)",
        experience: str = "средний",
        equipment: str = "зал",
        days_per_week: int = 4,
    ) -> Dict[str, Any]:
        prompt = (
            "Составь оптимальную программу тренировок для набора мышечной массы.\n"
            f"Цель: {goal}\n"
            f"Опыт: {experience}\n"
            f"Оборудование: {equipment}\n"
            f"Дней в неделю: {days_per_week}\n"
            "Включи базовые многосуставные движения с акцентом на прогрессию нагрузок, рабочие диапазоны повторений 6-12."
        )

        try:
            plan_schema: WorkoutPlanSchema = await self.gemini_service.call_structured(
                prompt=prompt,
                response_schema=WorkoutPlanSchema,
                timeout=18.0,
            )
            plan_json = json.dumps(plan_schema.model_dump(), ensure_ascii=False)
            plan_id = await self.workout_repo.save_plan(
                user_id=user_id,
                name=plan_schema.name,
                days_per_week=plan_schema.days_per_week,
                plan_data_json=plan_json,
                is_active=1,
            )
            return {
                "id": plan_id,
                "name": plan_schema.name,
                "days_per_week": plan_schema.days_per_week,
                "plan_data": plan_schema.model_dump(),
            }
        except Exception as e:
            logger.error(f"Failed to generate workout plan: {e}")
            # Fallback default push-pull-legs bulking plan
            fallback = self._get_fallback_plan(days_per_week)
            plan_json = json.dumps(fallback, ensure_ascii=False)
            plan_id = await self.workout_repo.save_plan(
                user_id=user_id,
                name=fallback["name"],
                days_per_week=days_per_week,
                plan_data_json=plan_json,
                is_active=1,
            )
            return {
                "id": plan_id,
                "name": fallback["name"],
                "days_per_week": days_per_week,
                "plan_data": fallback,
            }

    async def modify_plan(
        self,
        user_id: int,
        instruction: str
    ) -> Dict[str, Any]:
        active_plan = await self.workout_repo.get_active_plan(user_id)
        if not active_plan:
            # Generate new if none
            return await self.generate_plan(user_id)

        prompt = (
            "Ты опытный фитнес-тренер. Внеси запрошенные пользователем изменения в текущий тренировочный план.\n"
            "Остальные дни и упражнения сохрани без изменений.\n"
            f"<current_plan>{json.dumps(active_plan.get('plan_data', {}), ensure_ascii=False)}</current_plan>\n"
            f"<user_request>{instruction}</user_request>"
        )

        try:
            updated_schema: WorkoutPlanSchema = await self.gemini_service.call_structured(
                prompt=prompt,
                response_schema=WorkoutPlanSchema,
                timeout=18.0,
            )
            new_json = json.dumps(updated_schema.model_dump(), ensure_ascii=False)
            await self.workout_repo.update_plan_json(
                user_id=user_id,
                plan_id=active_plan["id"],
                plan_data_json=new_json,
                name=updated_schema.name,
            )
            return {
                "id": active_plan["id"],
                "name": updated_schema.name,
                "days_per_week": updated_schema.days_per_week,
                "plan_data": updated_schema.model_dump(),
            }
        except Exception as e:
            logger.error(f"Failed to modify workout plan: {e}")
            return active_plan

    def _get_fallback_plan(self, days: int) -> Dict[str, Any]:
        return {
            "name": "Базовая гипертрофия (Набор массы)",
            "days_per_week": days,
            "description": "Проверенный сплит для набора массы",
            "days": [
                {
                    "day_name": "День 1: Грудь и Трицепс",
                    "exercises": [
                        {"name": "Жим штанги лежа", "sets": 4, "reps": "8-10", "rest_sec": 120, "notes": "Базовое движение"},
                        {"name": "Жим гантелей под углом", "sets": 3, "reps": "10-12", "rest_sec": 90, "notes": "Фокус на верх груди"},
                        {"name": "Французский жим", "sets": 3, "reps": "10-12", "rest_sec": 75, "notes": "Чистая техника"},
                    ]
                },
                {
                    "day_name": "День 2: Спина и Бицепс",
                    "exercises": [
                        {"name": "Тяга верхнего блока / Подтягивания", "sets": 4, "reps": "8-10", "rest_sec": 120, "notes": "Широкий хват"},
                        {"name": "Тяга штанги в наклоне", "sets": 4, "reps": "8-10", "rest_sec": 120, "notes": "Контроль поясницы"},
                        {"name": "Подъем штанги на бицепс", "sets": 3, "reps": "10-12", "rest_sec": 75, "notes": "Без читинга"},
                    ]
                },
                {
                    "day_name": "День 3: Ноги и Плечи",
                    "exercises": [
                        {"name": "Приседания со штангой", "sets": 4, "reps": "8-10", "rest_sec": 150, "notes": "Глубокий сед"},
                        {"name": "Румынская тяга", "sets": 3, "reps": "10-12", "rest_sec": 120, "notes": "Фокус на бицепс бедра"},
                        {"name": "Армейский жим стоя", "sets": 4, "reps": "8-10", "rest_sec": 120, "notes": "Жим над головой"},
                    ]
                }
            ]
        }

    # =========================================================================
    # PROGRESSION RECOMMENDATIONS & SVG CHART
    # =========================================================================

    def get_progression_recommendation(
        self,
        exercise_name: str,
        current_weight: float,
        success: bool,
        recent_failures_count: int = 0
    ) -> Dict[str, Any]:
        """
        Progressive overload rule:
        - If success: add +2.5 kg (or +1.0 for light dumbbells)
        - If failure:
            - if 2 consecutive failures: maintain weight to solidify technique
            - else: retry same weight next session
        """
        clean = exercise_name.capitalize()
        if success:
            increment = 2.5 if current_weight >= 20.0 else 1.0
            next_weight = round(current_weight + increment, 1)
            reason = f"План успешно закрыт! На следующей тренировке добавляй +{increment} кг."
            status = "increment"
        else:
            next_weight = current_weight
            if recent_failures_count >= 2:
                reason = "2 тренировки подряд не закрыт план. Зафиксируй этот вес для оттачивания техники."
                status = "plateau_hold"
            else:
                reason = "Повтори этот же вес на следующей тренировке, сфокусируйся на восстановлении и сне."
                status = "retry"

        return {
            "exercise_name": clean,
            "current_weight": current_weight,
            "next_recommended_weight": next_weight,
            "status": status,
            "recommendation": reason,
        }

    def generate_svg_chart(self, exercise_name: str, logs: List[Dict[str, Any]]) -> str:
        """
        Generates lightweight self-contained SVG polyline chart of weights and PRs.
        """
        if not logs:
            return (
                '<svg viewBox="0 0 500 200" xmlns="http://www.w3.org/2000/svg" style="background:#1e1e24;border-radius:12px;">'
                '<text x="250" y="105" fill="#888" font-size="14" text-anchor="middle">Нет данных для графика</text>'
                '</svg>'
            )

        weights = [entry["weight_kg"] for entry in logs]
        min_w = max(0, min(weights) - 5)
        max_w = max(weights) + 5
        span_w = max(1.0, max_w - min_w)

        width = 460
        height = 160
        margin_x = 40
        margin_y = 20

        points = []
        dots = []
        n = len(logs)

        for i, entry in enumerate(logs):
            x = margin_x + (i * (width - 2 * margin_x) / max(1, n - 1))
            # Invert y: larger weight is higher (smaller y)
            y = margin_y + (height - 2 * margin_y) * (1.0 - (entry["weight_kg"] - min_w) / span_w)
            points.append(f"{x:.1f},{y:.1f}")

            dot_color = "#f59e0b" if entry.get("is_pr") else "#3b82f6"
            dot_r = "6" if entry.get("is_pr") else "4"
            dots.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{dot_r}" fill="{dot_color}" stroke="#fff" stroke-width="1.5"/>'
                f'<text x="{x:.1f}" y="{y - 8:.1f}" fill="#fff" font-size="10" text-anchor="middle">{entry["weight_kg"]}</text>'
            )

        polyline = " ".join(points)
        dots_svg = "\n".join(dots)

        return (
            f'<svg viewBox="0 0 {width} {height + 30}" xmlns="http://www.w3.org/2000/svg" '
            f'style="background:#161b22;border-radius:12px;width:100%;font-family:sans-serif;">\n'
            f'  <defs>\n'
            f'    <linearGradient id="grad_{exercise_name}" x1="0%" y1="0%" x2="0%" y2="100%">\n'
            f'      <stop offset="0%" stop-color="#3b82f6" stop-opacity="0.4"/>\n'
            f'      <stop offset="100%" stop-color="#3b82f6" stop-opacity="0.0"/>\n'
            f'    </linearGradient>\n'
            f'  </defs>\n'
            f'  <polyline fill="none" stroke="#3b82f6" stroke-width="3" stroke-linecap="round" points="{polyline}"/>\n'
            f'  {dots_svg}\n'
            f'  <text x="{margin_x}" y="{height + 20}" fill="#8b949e" font-size="11">{logs[0].get("workout_date", "")}</text>\n'
            f'  <text x="{width - margin_x}" y="{height + 20}" fill="#8b949e" font-size="11" text-anchor="end">{logs[-1].get("workout_date", "")}</text>\n'
            f'</svg>'
        )
