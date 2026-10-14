import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from app.database.connection import DatabaseManager
from app.database.models import CalorieGoalDB
from app.database.repositories.user_repository import UserRepository
from app.database.repositories.food_repository import FoodRepository
from app.database.repositories.expense_repository import ExpenseRepository
from app.database.repositories.productivity_repository import ProductivityRepository
from app.database.repositories.workout_repository import WorkoutRepository
from app.database.repositories.insights_repository import InsightsRepository
from app.services.gemini import GeminiService

logger = logging.getLogger(__name__)


# =========================================================================
# SCHEMAS FOR STRUCTURED GEMINI OUTPUT
# =========================================================================

class AdviceActionSchema(BaseModel):
    action_type: str = Field(
        ...,
        description="Type of action: increase_calorie_target | schedule_snack_reminder | add_shake_to_plan | none"
    )
    button_text: str = Field(..., description="Action button text in Russian, e.g. 'Повысить норму калорий на 200'")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parameters for executing the action")


class AdviceCardSchema(BaseModel):
    title: str = Field(..., description="Short encouraging title")
    problem_summary: str = Field(..., description="Problem identified from findings")
    recommendation: str = Field(..., description="Specific recommendation with calorie/protein numbers")
    action: AdviceActionSchema


class WeeklyAdviceOutputSchema(BaseModel):
    cards: List[AdviceCardSchema] = Field(..., min_length=3, max_length=3, description="Exactly 3 actionable advice cards")


# =========================================================================
# INSIGHTS SERVICE
# =========================================================================

class InsightsService:
    def __init__(
        self,
        db_manager: DatabaseManager,
        insights_repo: InsightsRepository,
        user_repo: UserRepository,
        food_repo: FoodRepository,
        expense_repo: ExpenseRepository,
        productivity_repo: ProductivityRepository,
        workout_repo: WorkoutRepository,
        gemini_service: GeminiService,
    ):
        self.db = db_manager
        self.insights_repo = insights_repo
        self.user_repo = user_repo
        self.food_repo = food_repo
        self.expense_repo = expense_repo
        self.productivity_repo = productivity_repo
        self.workout_repo = workout_repo
        self.gemini_service = gemini_service

    # =========================================================================
    # 1. DETERMINISTIC SQL AUDIT (5 DETECTORS + 14-DAY GATE)
    # =========================================================================

    async def audit_user(self, user_id: int) -> Dict[str, Any]:
        """
        Run 5 deterministic bulking detectors without calling Gemini.
        Requires >= 14 distinct days of data.
        """
        days_count = await self.insights_repo.get_distinct_log_days_count(user_id)
        if days_count < 14:
            days_needed = 14 - days_count
            return {
                "status": "insufficient_data",
                "days_available": days_count,
                "days_needed": 14,
                "message": f"Мало данных для выводов, нужно ещё {days_needed} дней",
                "findings": [],
            }

        findings = []

        # 1. Detector: «Ешь мало калорий для набора» (caloric_deficit_bulking)
        d1 = await self._detect_caloric_deficit(user_id)
        if d1:
            findings.append(d1)

        # 2. Detector: «Пропускаешь приёмы» (long_meal_gaps)
        d2 = await self._detect_long_meal_gaps(user_id)
        if d2:
            findings.append(d2)

        # 3. Detector: «Мало белка в дни тренировок» (low_protein_workout_days)
        d3 = await self._detect_low_protein_workout_days(user_id)
        if d3:
            findings.append(d3)

        # 4. Detector: «Вес стоит» (weight_stall)
        d4 = await self._detect_weight_stall(user_id)
        if d4:
            findings.append(d4)

        # 5. Detector: «Траты на снеки превышают бюджет на еду дома» (snacks_over_home_food)
        d5 = await self._detect_snacks_over_home_food(user_id)
        if d5:
            findings.append(d5)

        # Clear old findings and store new ones
        await self.insights_repo.clear_old_findings(user_id)
        for f in findings:
            await self.insights_repo.save_finding(
                user_id=user_id,
                finding_type=f["finding_type"],
                severity=f["severity"],
                evidence=f["evidence"],
                suggested_action=f.get("suggested_action"),
            )

        return {
            "status": "ok",
            "days_available": days_count,
            "findings_count": len(findings),
            "findings": findings,
        }

    # --- Detector Implementations ---

    async def _detect_caloric_deficit(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Average calories over last 14 days below target by > 10%."""
        goal = await self.user_repo.get_calorie_goal(user_id)
        target = goal.target_calories if goal else 2500

        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                """
                SELECT entry_date, SUM(total_calories) as daily_cals
                FROM food_entries
                WHERE user_id = ?
                GROUP BY entry_date
                ORDER BY entry_date DESC
                LIMIT 14
                """,
                (user_id,)
            )
            rows = await cur.fetchall()

        if not rows:
            return None

        daily_cals = [r["daily_cals"] for r in rows]
        avg_cals = sum(daily_cals) / len(daily_cals)

        if avg_cals < target * 0.90:
            def_pct = round((1 - (avg_cals / target)) * 100, 1)
            severity = "alert" if def_pct >= 20.0 else "warning"
            return {
                "finding_type": "caloric_deficit_bulking",
                "severity": severity,
                "title": "Ешь мало калорий для набора",
                "description": f"Средний калораж за 14 дней ({int(avg_cals)} ккал) ниже целевой нормы ({target} ккал) на {def_pct}%.",
                "evidence": {
                    "avg_calories": int(avg_cals),
                    "target_calories": target,
                    "deficit_percent": def_pct,
                    "days_sampled": len(daily_cals),
                },
                "suggested_action": "Повысить суточный калораж на 200-300 ккал за счёт питательных перекусов",
            }
        return None

    async def _detect_long_meal_gaps(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Meal intervals > 4.5h occurred on >= 3 days over the last 14 days."""
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                """
                SELECT entry_date, entry_time
                FROM food_entries
                WHERE user_id = ?
                ORDER BY entry_date DESC, entry_time ASC
                LIMIT 100
                """,
                (user_id,)
            )
            rows = await cur.fetchall()

        # Group by date
        from collections import defaultdict
        date_times = defaultdict(list)
        for r in rows:
            date_times[r["entry_date"]].append(r["entry_time"])

        long_gap_days = 0
        sample_dates = []
        for date_str, times in list(date_times.items())[:14]:
            parsed_minutes = []
            for t in sorted(times):
                try:
                    parts = t.split(":")
                    m = int(parts[0]) * 60 + int(parts[1])
                    parsed_minutes.append(m)
                except Exception:
                    continue

            # Check gaps between successive meals
            has_gap = False
            for i in range(len(parsed_minutes) - 1):
                diff = parsed_minutes[i + 1] - parsed_minutes[i]
                if diff >= 270:  # 4.5 hours = 270 mins
                    has_gap = True
                    break

            if has_gap:
                long_gap_days += 1
                sample_dates.append(date_str)

        if long_gap_days >= 3:
            return {
                "finding_type": "long_meal_gaps",
                "severity": "warning",
                "title": "Пропускаешь приёмы пищи",
                "description": f"Перерывы между приёмами пищи более 4.5 часов зафиксированы в {long_gap_days} днях за последнее время.",
                "evidence": {
                    "long_gap_days_count": long_gap_days,
                    "sample_dates": sample_dates[:3],
                    "threshold_hours": 4.5,
                },
                "suggested_action": "Запланировать постоянный перекус на 16:00 между обедом и ужином",
            }
        return None

    async def _detect_low_protein_workout_days(self, user_id: int) -> Optional[Dict[str, Any]]:
        """In workout days, protein intake is below 1.6g / kg."""
        # Get workout days in the last 14 days
        async with self.db.get_connection() as conn:
            cur_w = await conn.execute(
                """
                SELECT DISTINCT workout_date FROM workout_logs
                WHERE user_id = ? ORDER BY workout_date DESC LIMIT 14
                """,
                (user_id,)
            )
            w_rows = await cur_w.fetchall()

        if not w_rows:
            return None

        workout_dates = [r["workout_date"] for r in w_rows]

        # Get user weight or target protein
        weights = await self.food_repo.get_recent_weights(user_id, limit=1)
        user_weight = weights[0]["weight_kg"] if weights else 70.0
        min_protein_needed = round(user_weight * 1.6)

        low_protein_count = 0
        for wd in workout_dates:
            async with self.db.get_connection() as conn:
                cur_p = await conn.execute(
                    "SELECT COALESCE(SUM(total_protein), 0.0) as p_total FROM food_entries WHERE user_id = ? AND entry_date = ?",
                    (user_id, wd)
                )
                r_p = await cur_p.fetchone()
                p_consumed = float(r_p["p_total"]) if r_p else 0.0
                if p_consumed < min_protein_needed:
                    low_protein_count += 1

        if low_protein_count >= 2:
            return {
                "finding_type": "low_protein_workout_days",
                "severity": "warning",
                "title": "Мало белка в дни тренировок",
                "description": f"В {low_protein_count} из {len(workout_dates)} тренировочных дней потреблено менее {min_protein_needed} г белка (< 1.6 г/кг).",
                "evidence": {
                    "workout_days": len(workout_dates),
                    "low_protein_days": low_protein_count,
                    "target_protein_per_day": min_protein_needed,
                },
                "suggested_action": "Добавить 30-40 г белка сразу после тренировки (протеин, творог или куриное филе)",
            }
        return None

    async def _detect_weight_stall(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Average weight of last 7 days is <= average weight of previous 7 days (days 8-14)."""
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                """
                SELECT weight_kg, log_date FROM weight_logs
                WHERE user_id = ? ORDER BY log_date DESC LIMIT 14
                """,
                (user_id,)
            )
            rows = await cur.fetchall()

        if len(rows) < 6:
            return None

        recent_slice = rows[: len(rows) // 2]
        prev_slice = rows[len(rows) // 2 :]

        avg_recent = sum(r["weight_kg"] for r in recent_slice) / len(recent_slice)
        avg_prev = sum(r["weight_kg"] for r in prev_slice) / len(prev_slice)

        if avg_recent <= avg_prev:
            delta = round(avg_recent - avg_prev, 2)
            return {
                "finding_type": "weight_stall",
                "severity": "alert",
                "title": "Вес стоит на месте",
                "description": f"Средний вес за последнюю неделю ({avg_recent:.1f} кг) не вырос относительно предыдущей недели ({avg_prev:.1f} кг, дельта {delta:+.2f} кг).",
                "evidence": {
                    "recent_avg_kg": round(avg_recent, 2),
                    "prev_avg_kg": round(avg_prev, 2),
                    "delta_kg": delta,
                },
                "suggested_action": "Повысить суточную норму калорий на +200 ккал для возобновления роста массы",
            }
        return None

    async def _detect_snacks_over_home_food(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Compare spending on snacks/impulse items vs groceries."""
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                """
                SELECT 
                    COALESCE(SUM(CASE WHEN is_impulse = 1 OR category = 'snacks' THEN amount ELSE 0 END), 0.0) as snacks_total,
                    COALESCE(SUM(CASE WHEN is_impulse = 0 AND (category = 'food' OR category = 'groceries') THEN amount ELSE 0 END), 0.0) as home_food_total
                FROM expenses
                WHERE user_id = ? AND expense_date >= date('now', '-30 days')
                """,
                (user_id,)
            )
            row = await cur.fetchone()

        if not row:
            return None

        snacks = float(row["snacks_total"])
        home_food = float(row["home_food_total"])

        if snacks > home_food and snacks > 3000.0:
            return {
                "finding_type": "snacks_over_home_food",
                "severity": "warning",
                "title": "Траты на снеки превышают бюджет на еду дома",
                "description": f"За месяц на снеки и импульсивную еду потрачено {int(snacks):,} ₸, а на основные продукты — всего {int(home_food):,} ₸.",
                "evidence": {
                    "snacks_total": snacks,
                    "home_food_total": home_food,
                },
                "suggested_action": "Сформировать недельный список покупок круп и мяса, чтобы готовить сытную еду дома",
            }
        return None

    # =========================================================================
    # 2. WEEKLY GEMINI ADVICE GENERATOR (3 ACTION CARDS)
    # =========================================================================

    async def generate_weekly_advice(self, user_id: int) -> Dict[str, Any]:
        """
        Run audit, pass top findings to Gemini with structured output, and return 3 actionable cards.
        """
        audit_res = await self.audit_user(user_id)
        findings = audit_res.get("findings", [])

        # Default fallback cards in case Gemini is unavailable or findings are empty
        cards = self._build_fallback_cards(findings)

        if self.gemini_service:
            try:
                system_prompt = (
                    "Ты — спортивный нутрициолог и финансовый коуч супер-приложения для набора мышечной массы.\n"
                    "Проанализируй детерминированные находки аудита пользователя и сформируй ровно 3 конкретных совета.\n"
                    "Каждый совет ДОЛЖЕН содержать действие с кнопкой ('action'), которое реально меняет параметры приложения:\n"
                    "- 'increase_calorie_target': params {'calorie_delta': 200}\n"
                    "- 'schedule_snack_reminder': params {'time': '16:00', 'text': '🍎 Перекус для массы (+300 ккал)'}\n"
                    "- 'add_shake_to_plan': params {'shake_name': 'Белково-углеводный шейк', 'calories': 550, 'protein_g': 45}\n"
                    "Пиши кратко, дружелюбно, мотивирующе, на русском языке."
                )

                findings_text = json.dumps(findings, ensure_ascii=False) if findings else "Данные в норме, продолжай прогрессировать."
                user_prompt = f"<user_findings>\n{findings_text}\n</user_findings>"

                response = await self.gemini_service.call_structured(
                    prompt=user_prompt,
                    response_schema=WeeklyAdviceOutputSchema,
                    system_instruction=system_prompt,
                )

                if response and hasattr(response, "cards") and len(response.cards) == 3:
                    cards = [card.model_dump() for card in response.cards]
            except Exception as e:
                logger.warning(f"Gemini weekly advice generation failed, falling back to deterministic cards: {e}")

        # Current monday as week_start
        today = datetime.utcnow().date()
        week_start = (today - timedelta(days=today.weekday())).isoformat()

        advice_payload = {"cards": cards}
        advice_id = await self.insights_repo.save_ai_advice(user_id, week_start, advice_payload)

        return {
            "id": advice_id,
            "week_start": week_start,
            "status": "pending",
            "cards": cards,
        }

    def _build_fallback_cards(self, findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """High-quality deterministic bulking cards."""
        card1 = {
            "title": "Добавь высококалорийный шейк после зала",
            "problem_summary": "Недобор калорий и белка в тренировочные дни замедляет рост мышц.",
            "recommendation": "После тренировки пей шейк (молоко, банан, овсянка, арахисовая паста) — это даст +550 ккал и 35 г белка за 2 минуты.",
            "action": {
                "action_type": "add_shake_to_plan",
                "button_text": "Добавить шейк в план питания",
                "params": {"shake_name": "Шейк для массы (банан + паста)", "calories": 550, "protein_g": 35},
            },
        }

        card2 = {
            "title": "Подними планку суточных калорий",
            "problem_summary": "При наборе массы необходим стабильный профицит энергии.",
            "recommendation": "Увеличь суточную цель на 200 ккал, чтобы выйти из плато и возобновить рост веса.",
            "action": {
                "action_type": "increase_calorie_target",
                "button_text": "Повысить норму калорий на 200",
                "params": {"calorie_delta": 200},
            },
        }

        card3 = {
            "title": "Запланируй перекус на 16:00",
            "problem_summary": "Большие перерывы между обедом и ужином приводят к катаболизму и вечернему перееданию снеков.",
            "recommendation": "Поставь напоминание на 16:00 для порции орехов или творога с мёдом (+300 ккал).",
            "action": {
                "action_type": "schedule_snack_reminder",
                "button_text": "Запланировать перекус на 16:00",
                "params": {"time": "16:00", "text": "🍎 Время перекуса для набора массы! (+300 ккал)"},
            },
        }

        return [card1, card2, card3]

    # =========================================================================
    # 3. APPLY & UNDO ADVICE ACTION
    # =========================================================================

    async def apply_advice_action(self, user_id: int, advice_id: int, card_index: int) -> Dict[str, Any]:
        """Apply the action from one of the advice cards, recording undo info."""
        advice_item = await self.insights_repo.get_ai_advice_by_id(user_id, advice_id)
        if not advice_item:
            raise ValueError(f"Advice id {advice_id} not found")

        cards = advice_item.get("advice", {}).get("cards", [])
        if card_index < 0 or card_index >= len(cards):
            raise ValueError(f"Invalid card index {card_index}")

        card = cards[card_index]
        action = card.get("action", {})
        action_type = action.get("action_type")
        params = action.get("params", {})

        undo_payload = {"action_type": action_type}

        if action_type == "increase_calorie_target":
            delta = int(params.get("calorie_delta", 200))
            goal = await self.user_repo.get_calorie_goal(user_id)
            if goal:
                undo_payload["old_calories"] = goal.target_calories
                goal.target_calories += delta
                await self.user_repo.save_calorie_goal(goal)
            else:
                undo_payload["old_calories"] = 2500
                new_goal = CalorieGoalDB(
                    user_id=user_id,
                    bmr=1700,
                    tdee=2300,
                    target_calories=2500 + delta,
                    target_protein_g=150,
                    target_fat_g=70,
                    target_carbs_g=300,
                )
                await self.user_repo.save_calorie_goal(new_goal)

        elif action_type == "schedule_snack_reminder":
            time_str = params.get("time", "16:00")
            msg_text = params.get("text", "🍎 Время перекуса для набора массы! (+300 ккал)")
            now_ts = int(datetime.utcnow().timestamp())
            sched_id = await self.productivity_repo.save_schedule(
                user_id=user_id,
                job_type="reminder",
                scheduled_time=time_str,
                next_run_at=now_ts,
                data_json=json.dumps({"text": msg_text, "daily_time": time_str}, ensure_ascii=False),
            )
            undo_payload["schedule_id"] = sched_id

        elif action_type == "add_shake_to_plan":
            name = params.get("shake_name", "Шейк для массы")
            cals = int(params.get("calories", 550))
            prot = float(params.get("protein_g", 35.0))
            async with self.db.get_connection() as conn:
                cur = await conn.execute(
                    """
                    INSERT INTO custom_foods (user_id, name, calories_per_100g, protein_per_100g, fat_per_100g, carbs_per_100g, is_favorite, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now'))
                    """,
                    (user_id, name, cals, prot, 15.0, 60.0)
                )
                undo_payload["custom_food_id"] = cur.lastrowid
                await conn.commit()

        await self.insights_repo.mark_advice_applied(user_id, advice_id, card_index, undo_payload)

        return {
            "status": "applied",
            "card_index": card_index,
            "action": action,
            "message": f"Действие '{action.get('button_text')}' успешно применено!",
        }

    async def undo_advice_action(self, user_id: int, advice_id: int) -> Dict[str, Any]:
        """Undo the previously applied action."""
        advice_item = await self.insights_repo.get_ai_advice_by_id(user_id, advice_id)
        if not advice_item:
            raise ValueError(f"Advice id {advice_id} not found")

        advice_data = advice_item.get("advice", {})
        undo_payload = advice_data.get("undo_payload", {})
        action_type = undo_payload.get("action_type")

        if action_type == "increase_calorie_target":
            old_cals = undo_payload.get("old_calories")
            if old_cals:
                goal = await self.user_repo.get_calorie_goal(user_id)
                if goal:
                    goal.target_calories = old_cals
                    await self.user_repo.save_calorie_goal(goal)

        elif action_type == "schedule_snack_reminder":
            sched_id = undo_payload.get("schedule_id")
            if sched_id:
                await self.productivity_repo.deactivate_schedule(sched_id)

        elif action_type == "add_shake_to_plan":
            cf_id = undo_payload.get("custom_food_id")
            if cf_id:
                async with self.db.get_connection() as conn:
                    await conn.execute("DELETE FROM custom_foods WHERE id = ? AND user_id = ?", (cf_id, user_id))
                    await conn.commit()

        await self.insights_repo.mark_advice_undone(user_id, advice_id)

        return {
            "status": "undone",
            "message": "Действие успешно отменено.",
        }

    # =========================================================================
    # 4. TWO-WEEK EFFECT EVALUATION
    # =========================================================================

    async def evaluate_advice_effect(self, advice_id: int) -> Optional[Dict[str, Any]]:
        """
        Evaluate if the applied advice worked 2 weeks later.
        «Совет сработал: +600 г за 2 недели»
        """
        async with self.db.get_connection() as conn:
            cur = await conn.execute("SELECT * FROM ai_advice WHERE id = ?;", (advice_id,))
            row = await cur.fetchone()
            if not row:
                return None
            item = dict(row)

        user_id = item["user_id"]
        weights = await self.food_repo.get_recent_weights(user_id, limit=14)
        if len(weights) >= 2:
            latest_w = weights[0]["weight_kg"]
            initial_w = weights[-1]["weight_kg"]
            delta = round(latest_w - initial_w, 2)
            if delta > 0:
                result_text = f"Совет сработал: +{int(delta * 1000)} г за 2 недели! Масса растёт ✅"
            elif delta == 0:
                result_text = "Вес стабилен: для ускорения набора массы увеличь порции углеводов."
            else:
                result_text = f"Вес снизился на {abs(delta):.1f} кг: необходимо строго закрывать норму калорий."
        else:
            result_text = "Совет применён: дисциплина питания улучшилась!"

        await self.insights_repo.mark_advice_effect(advice_id, result_text)

        return {
            "advice_id": advice_id,
            "effect_result": result_text,
        }
