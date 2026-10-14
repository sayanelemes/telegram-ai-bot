import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from app.config.settings import settings
from app.database.repositories.user_repository import UserRepository
from app.database.repositories.productivity_repository import ProductivityRepository
from app.database.repositories.food_repository import FoodRepository

logger = logging.getLogger(__name__)


class UnifiedSchedulerService:
    """
    Unified 1-minute tick scheduler based on APScheduler and SQLite `schedules` table.
    Handles:
    - 1-minute tick processing due schedules (reminders, morning summary, evening checkout, habit threats)
    - Bulking hunger detector ("Давно не ел", >= 3.5h gap or skipped morning food, deficit > 150 kcal)
    - Morning summary at 09:00 (weight delta, target macros, workout plan, top-3 tasks)
    - Evening checkout at 21:30 (consumed vs target, water, habits, satiety rating 1-5)
    - Habit streak threats at 20:00
    - User modes awareness (DND, Sick, Travel)
    """

    def __init__(
        self,
        productivity_repo: ProductivityRepository,
        user_repo: UserRepository,
        food_repo: FoodRepository,
        bot: Optional[Bot] = None,
    ):
        self.productivity_repo = productivity_repo
        self.user_repo = user_repo
        self.food_repo = food_repo
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self._last_hunger_alert: Dict[int, int] = {}  # user_id -> timestamp
        self._alerted_subs: set = set()  # "sub_id:date" -> alerted

    def set_bot(self, bot: Bot) -> None:
        self.bot = bot

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.add_job(
                func=self.tick,
                trigger=IntervalTrigger(minutes=1),
                id="unified_scheduler_tick",
                name="Unified 1-minute Scheduler Tick",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
            )
            self.scheduler.start()
            logger.info("UnifiedSchedulerService started with 1-minute tick.")

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("UnifiedSchedulerService stopped.")

    # =========================================================================
    # CORE 1-MINUTE TICK
    # =========================================================================

    async def tick(self, now_ts: Optional[int] = None) -> List[Dict[str, Any]]:
        """Executed once every minute by APScheduler."""
        if now_ts is None:
            now_ts = int(datetime.now(timezone.utc).timestamp())

        logger.debug(f"Unified scheduler tick at timestamp {now_ts}")
        processed = []

        try:
            due_items = await self.productivity_repo.get_due_schedules(now_ts)
            for item in due_items:
                try:
                    result = await self._process_schedule_item(item, now_ts)
                    if result:
                        processed.append(result)
                except Exception as ex:
                    logger.error(f"Error processing schedule item {item.get('id')}: {ex}", exc_info=True)

            # Also check hunger for active users
            await self._run_hunger_checks(now_ts)
            await self._run_subscription_checks(now_ts)

        except Exception as e:
            logger.error(f"Unified scheduler tick error: {e}", exc_info=True)

        return processed

    async def _process_schedule_item(self, item: Dict[str, Any], now_ts: int) -> Optional[Dict[str, Any]]:
        user_id = item["user_id"]
        job_type = item["job_type"]
        schedule_id = item["id"]

        user = await self.user_repo.get_by_id(user_id)
        if not user:
            await self.productivity_repo.deactivate_schedule(schedule_id)
            return None

        # Check user modes
        modes = await self.productivity_repo.get_active_modes(user_id)
        if modes.get("dnd") and job_type != "urgent":
            # In DND mode: postpone reminder by 30 mins
            new_run = now_ts + 30 * 60
            await self.productivity_repo.update_schedule_next_run(schedule_id, new_run)
            return {"schedule_id": schedule_id, "action": "postponed_dnd", "new_run": new_run}

        if modes.get("sick") and job_type in ("workout", "aggressive_hunger"):
            # Suppress or postpone
            new_run = now_ts + 24 * 3600
            await self.productivity_repo.update_schedule_next_run(schedule_id, new_run)
            return {"schedule_id": schedule_id, "action": "suppressed_sick", "new_run": new_run}

        payload = {}
        if item.get("data_json"):
            try:
                payload = json.loads(item["data_json"])
            except Exception:
                payload = {}

        if job_type == "morning_summary":
            text = await self.build_morning_summary(user_id)
            markup = self._get_morning_keyboard()
            await self._send_message(user.telegram_id, text, markup)
            # Reschedule for tomorrow 09:00
            next_run = self._calc_next_daily_ts(user.timezone, hour=9, minute=0, from_ts=now_ts)
            await self.productivity_repo.update_schedule_next_run(schedule_id, next_run)
            return {"schedule_id": schedule_id, "action": "executed", "type": job_type}

        elif job_type == "evening_checkout":
            text = await self.build_evening_checkout(user_id)
            markup = self._get_satiety_keyboard()
            await self._send_message(user.telegram_id, text, markup)
            # Reschedule for tomorrow 21:30
            next_run = self._calc_next_daily_ts(user.timezone, hour=21, minute=30, from_ts=now_ts)
            await self.productivity_repo.update_schedule_next_run(schedule_id, next_run)
            return {"schedule_id": schedule_id, "action": "executed", "type": job_type}

        elif job_type == "habit_threat":
            text = await self.build_habit_threat_message(user_id)
            if text:
                markup = self._get_app_link_keyboard()
                await self._send_message(user.telegram_id, text, markup)
            # Reschedule for tomorrow 20:00
            next_run = self._calc_next_daily_ts(user.timezone, hour=20, minute=0, from_ts=now_ts)
            await self.productivity_repo.update_schedule_next_run(schedule_id, next_run)
            return {"schedule_id": schedule_id, "action": "executed", "type": job_type}

        elif job_type == "reminder":
            msg_text = payload.get("text", "⏰ Напоминание!")
            markup = self._get_snooze_keyboard(schedule_id)
            await self._send_message(user.telegram_id, msg_text, markup)

            # Check if recurring or one-off
            interval_hours = payload.get("interval_hours", 0)
            if interval_hours and interval_hours > 0:
                next_run = now_ts + interval_hours * 3600
                await self.productivity_repo.update_schedule_next_run(schedule_id, next_run)
            elif payload.get("daily_time"):
                parts = payload["daily_time"].split(":")
                h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
                next_run = self._calc_next_daily_ts(user.timezone, hour=h, minute=m, from_ts=now_ts)
                await self.productivity_repo.update_schedule_next_run(schedule_id, next_run)
            else:
                # One-off
                await self.productivity_repo.deactivate_schedule(schedule_id)
            return {"schedule_id": schedule_id, "action": "executed", "type": job_type}

        return None

    # =========================================================================
    # HUNGER / BULKING GAP DETECTOR
    # =========================================================================

    async def _run_hunger_checks(self, now_ts: int) -> None:
        """Check all users who have hunger detector enabled."""
        # Check users from recent schedules or active users
        active_schedules = await self.productivity_repo.get_due_schedules(now_ts + 60)
        user_ids = {s["user_id"] for s in active_schedules}
        for uid in user_ids:
            try:
                await self.check_hunger_for_user(uid, now_ts)
            except Exception as e:
                logger.error(f"Failed hunger check for user {uid}: {e}")

    async def check_hunger_for_user(self, user_id: int, now_ts: Optional[int] = None) -> bool:
        """
        Hunger Detector rules:
        - Deficit > 150 kcal
        - Last food >= 3.5h ago (or >= 09:00 with 0 meals)
        - Last hunger alert > 2h ago
        - Not in DND or Sick mode
        - User daytime (between 09:00 and 22:30)
        """
        if now_ts is None:
            now_ts = int(datetime.now(timezone.utc).timestamp())

        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return False

        modes = await self.productivity_repo.get_active_modes(user_id)
        if modes.get("dnd") or modes.get("sick"):
            return False

        # Check last alert cooldown (2 hours)
        last_alert = self._last_hunger_alert.get(user_id, 0)
        if (now_ts - last_alert) < 2 * 3600:
            return False

        # Check daytime
        tz_str = user.timezone or "Asia/Almaty"
        try:
            tz = ZoneInfo(tz_str)
        except Exception:
            tz = ZoneInfo("Asia/Almaty")
        user_dt = datetime.fromtimestamp(now_ts, tz=tz)
        if user_dt.hour < 9 or user_dt.hour >= 22 or (user_dt.hour == 22 and user_dt.minute > 30):
            return False

        today_str = user_dt.date().isoformat()
        entries = await self.food_repo.get_user_food_entries(user_id, today_str)

        consumed_cals = sum(it.calories for e in entries for it in e.items)
        goal = await self.user_repo.get_calorie_goal(user_id)
        target_cals = goal.target_calories if goal else 2500

        from app.database.repositories.workout_repository import WorkoutRepository
        w_repo = WorkoutRepository(self.productivity_repo.db)
        if await w_repo.has_workout_today(user_id, today_str):
            target_cals = round(target_cals * 1.10)

        deficit = target_cals - consumed_cals

        if deficit <= 150:
            return False

        # Check time since last food
        should_alert = False
        if not entries:
            # 0 meals logged today and it's >= 09:00
            if user_dt.hour >= 9:
                should_alert = True
        else:
            # Find latest entry created_at
            latest_time_ts = 0
            for e in entries:
                try:
                    dt = datetime.fromisoformat(e.created_at)
                    t = int(dt.timestamp())
                    if t > latest_time_ts:
                        latest_time_ts = t
                except Exception:
                    pass
            if latest_time_ts > 0 and (now_ts - latest_time_ts) >= int(3.5 * 3600):
                should_alert = True

        if should_alert:
            self._last_hunger_alert[user_id] = now_ts
            await self._send_hunger_alert(user.telegram_id, deficit)
            return True

        return False

    async def _send_hunger_alert(self, telegram_id: int, deficit: int) -> None:
        text = (
            "🍽 <b>Пора подкрепиться!</b>\n\n"
            f"Ты не ел уже более 3.5 часов, а до суточной нормы калорий не хватает ещё <b>{deficit} ккал</b>.\n"
            "Для набора мышечной массы важно поддерживать регулярный приток энергии и строительного белка!"
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🍽 Рецепт под дефицит",
                        web_app=WebAppInfo(url=f"{settings.WEB_APP_URL}?screen=recipe&remaining={deficit}")
                        if settings.WEB_APP_URL else None,
                        url=settings.WEB_APP_URL or "https://t.me"
                    )
                ],
                [
                    InlineKeyboardButton(text="⚡️ Быстрый шейк (550 ккал)", callback_data="quick_shake"),
                    InlineKeyboardButton(text="⏳ Позже на 30 мин", callback_data="snooze_hunger:30"),
                ]
            ]
        )
        await self._send_message(telegram_id, text, markup)

    async def _run_subscription_checks(self, now_ts: int) -> None:
        """
        Check subscriptions due tomorrow and send advance reminder.
        «Завтра списание 2 990 ₸ за Яндекс Плюс. Продлеваем?»
        """
        try:
            from app.database.repositories.finance_repository import FinanceRepository
            from app.utils.formatters import format_currency

            finance_repo = FinanceRepository(self.productivity_repo.db)

            async with self.productivity_repo.db.get_connection() as conn:
                cur = await conn.execute("SELECT DISTINCT user_id FROM subscriptions")
                rows = await cur.fetchall()
                user_ids = [r["user_id"] for r in rows]

            for uid in user_ids:
                user = await self.user_repo.get_by_id(uid)
                if not user or not user.telegram_id:
                    continue

                tz_str = user.timezone or "Asia/Almaty"
                try:
                    tz = ZoneInfo(tz_str)
                except Exception:
                    tz = ZoneInfo("Asia/Almaty")

                tomorrow_str = (datetime.fromtimestamp(now_ts, tz=tz) + timedelta(days=1)).date().isoformat()

                modes = await self.productivity_repo.get_active_modes(uid)
                if modes.get("dnd"):
                    continue

                subs = await finance_repo.get_subscriptions(uid)
                for sub in subs:
                    if sub.get("next_payment_date") == tomorrow_str:
                        alert_key = f"{sub['id']}:{tomorrow_str}"
                        if alert_key not in self._alerted_subs:
                            amt_str = format_currency(sub["amount"], sub.get("currency", "₸"))
                            name = sub["name"]
                            text = (
                                "💳 <b>Напоминание о подписке</b>\n\n"
                                f"Завтра списание <b>{amt_str}</b> за <b>{name}</b>. Продлеваем?"
                            )
                            markup = InlineKeyboardMarkup(
                                inline_keyboard=[
                                    [
                                        InlineKeyboardButton(
                                            text="💳 Открыть финансы",
                                            web_app=WebAppInfo(url=f"{settings.WEB_APP_URL}?screen=money")
                                            if settings.WEB_APP_URL else None,
                                            url=settings.WEB_APP_URL or "https://t.me",
                                        )
                                    ]
                                ]
                            )
                            await self._send_message(user.telegram_id, text, markup)
                            self._alerted_subs.add(alert_key)
        except Exception as e:
            logger.error(f"Subscription checks error: {e}", exc_info=True)

    # =========================================================================
    # SUMMARY BUILDERS
    # =========================================================================

    async def build_morning_summary(self, user_id: int) -> str:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return "Доброе утро!"

        tz_str = user.timezone or "Asia/Almaty"
        try:
            tz = ZoneInfo(tz_str)
        except Exception:
            tz = ZoneInfo("Asia/Almaty")
        today_str = datetime.now(tz=tz).date().isoformat()

        # Weight delta
        weights = await self.food_repo.get_recent_weights(user_id, limit=2)
        if weights:
            today_w = weights[0]["weight_kg"]
            if len(weights) > 1:
                yesterday_w = weights[1]["weight_kg"]
                delta = today_w - yesterday_w
                delta_str = f" ({delta:+.1f} кг со вчера)"
            else:
                delta_str = ""
            weight_line = f"⚖️ Вес: <b>{today_w:.1f} кг</b>{delta_str}"
        else:
            weight_line = "⚖️ Вес: <i>ещё не записан сегодня</i>"

        # Targets
        goal = await self.user_repo.get_calorie_goal(user_id)
        cals = goal.target_calories if goal else 2500
        p = goal.target_protein_g if goal else 150
        f = goal.target_fat_g if goal else 80
        c = goal.target_carbs_g if goal else 300
        targets_line = f"🎯 План питания: <b>{cals} ккал</b> (Б {p}г / Ж {f}г / У {c}г)"

        # Workout status
        modes = await self.productivity_repo.get_active_modes(user_id)
        if modes.get("sick"):
            workout_line = "🏋️ Тренировка: <i>на паузе (режим восстановления 🤒)</i>"
        elif modes.get("travel"):
            workout_line = "🏋️ Тренировка: <i>выездной режим (без зала ✈️)</i>"
        else:
            workout_line = "🏋️ Тренировка: <b>День тренировки</b> (не забудь перед залом перекусить за 1.5ч!)"

        # Top 3 urgent tasks
        top_tasks = await self.productivity_repo.get_top_urgent_tasks(user_id, limit=3)
        if top_tasks:
            tasks_str = "\n".join(f"  ▫️ {t['title']}" for t in top_tasks)
            tasks_block = f"📋 <b>Главные задачи на сегодня:</b>\n{tasks_str}"
        else:
            tasks_block = "📋 <b>Задачи:</b> список пуст, отличный день для прогресса!"

        return (
            "🌅 <b>Утренняя сводка (09:00)</b>\n\n"
            f"{weight_line}\n"
            f"{targets_line}\n"
            f"{workout_line}\n\n"
            f"{tasks_block}"
        )

    async def build_evening_checkout(self, user_id: int) -> str:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return "Добрый вечер!"

        tz_str = user.timezone or "Asia/Almaty"
        try:
            tz = ZoneInfo(tz_str)
        except Exception:
            tz = ZoneInfo("Asia/Almaty")
        today_str = datetime.now(tz=tz).date().isoformat()

        entries = await self.food_repo.get_user_food_entries(user_id, today_str)
        consumed_cals = sum(it.calories for e in entries for it in e.items)
        consumed_p = sum(it.protein_g for e in entries for it in e.items)

        goal = await self.user_repo.get_calorie_goal(user_id)
        target_cals = goal.target_calories if goal else 2500
        target_p = goal.target_protein_g if goal else 150

        from app.database.repositories.workout_repository import WorkoutRepository
        w_repo = WorkoutRepository(self.productivity_repo.db)
        if await w_repo.has_workout_today(user_id, today_str):
            target_cals = round(target_cals * 1.10)

        cal_def = target_cals - consumed_cals
        p_def = target_p - consumed_p

        if cal_def > 0:
            food_line = (
                f"🍽 Съедено: <b>{consumed_cals} / {target_cals} ккал</b>\n"
                f"⚠️ Нехватка: <b>{cal_def} ккал</b> (белок: {consumed_p:.0f}/{target_p} г, не хватает {p_def:.0f}г)"
            )
        else:
            food_line = (
                f"🍽 Съедено: <b>{consumed_cals} / {target_cals} ккал</b>\n"
                f"🔥 Норма выполнена (+{abs(cal_def)} ккал перекрытия)! Белок: {consumed_p:.0f}/{target_p} г ✅"
            )

        water = await self.food_repo.get_total_water_for_day(user_id, today_str)
        water_target = getattr(user, "water_target_ml", 2500) or 2500
        water_line = f"💧 Вода: <b>{water} / {water_target} мл</b>"

        # Habit streak check
        pending_habits = await self.productivity_repo.get_pending_habits_for_today(user_id, today_str)
        if pending_habits:
            habits_line = "⚠️ Не закрыты привычки: " + ", ".join(h["name"] for h in pending_habits)
        else:
            habits_line = "✅ Все привычки на сегодня выполнены!"

        return (
            "🌙 <b>Вечерний чекаут (21:30)</b>\n\n"
            f"{food_line}\n"
            f"{water_line}\n"
            f"{habits_line}\n\n"
            "Оцени уровень сытости и самочувствия за день:"
        )

    async def build_habit_threat_message(self, user_id: int) -> Optional[str]:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None

        tz_str = user.timezone or "Asia/Almaty"
        try:
            tz = ZoneInfo(tz_str)
        except Exception:
            tz = ZoneInfo("Asia/Almaty")
        today_str = datetime.now(tz=tz).date().isoformat()

        pending = await self.productivity_repo.get_pending_habits_for_today(user_id, today_str)
        if not pending:
            return None

        habits_list = "\n".join(f"• <b>{h['name']}</b> (текущий стрик: {h.get('streak', 0)} дн)" for h in pending)
        return (
            "⚠️ <b>Угроза срыва привычек!</b>\n\n"
            "До конца дня осталось мало времени, а эти привычки ещё не закрыты:\n"
            f"{habits_list}\n\n"
            "Не дай сгореть своему прогрессу — зайди в приложение и отметь выполнение!"
        )

    # =========================================================================
    # SNOOZE & KEYBOARDS
    # =========================================================================

    async def snooze(self, schedule_id: int, minutes: int, now_ts: Optional[int] = None) -> int:
        if now_ts is None:
            now_ts = int(datetime.now(timezone.utc).timestamp())
        return await self.productivity_repo.snooze_schedule(schedule_id, minutes, now_ts)

    def _get_snooze_keyboard(self, schedule_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="⏳ 15 мин", callback_data=f"snooze_rem:15:{schedule_id}"),
                    InlineKeyboardButton(text="⏳ 30 мин", callback_data=f"snooze_rem:30:{schedule_id}"),
                    InlineKeyboardButton(text="⏳ 1 час", callback_data=f"snooze_rem:60:{schedule_id}"),
                ]
            ]
        )

    def _get_satiety_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="1️⃣ Голод", callback_data="satiety:1"),
                    InlineKeyboardButton(text="2️⃣ Мало", callback_data="satiety:2"),
                    InlineKeyboardButton(text="3️⃣ Норма", callback_data="satiety:3"),
                    InlineKeyboardButton(text="4️⃣ Сыт", callback_data="satiety:4"),
                    InlineKeyboardButton(text="5️⃣ Сыт++", callback_data="satiety:5"),
                ]
            ]
        )

    def _get_morning_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🚀 Открыть приложение",
                        web_app=WebAppInfo(url=settings.WEB_APP_URL) if settings.WEB_APP_URL else None,
                        url=settings.WEB_APP_URL or "https://t.me"
                    )
                ]
            ]
        )

    def _get_app_link_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Отметить привычки",
                        web_app=WebAppInfo(url=f"{settings.WEB_APP_URL}?screen=habits") if settings.WEB_APP_URL else None,
                        url=settings.WEB_APP_URL or "https://t.me"
                    )
                ]
            ]
        )

    async def _send_message(
        self,
        telegram_id: int,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> None:
        if not self.bot:
            logger.warning("Bot instance not set on UnifiedSchedulerService, message skipped.")
            return
        try:
            await self.bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            logger.info(f"UnifiedScheduler sent message to {telegram_id}")
        except Exception as e:
            logger.error(f"Failed to send scheduler message to {telegram_id}: {e}")

    def _calc_next_daily_ts(self, tz_str: str, hour: int, minute: int, from_ts: int) -> int:
        try:
            tz = ZoneInfo(tz_str)
        except Exception:
            tz = ZoneInfo("Asia/Almaty")
        from_dt = datetime.fromtimestamp(from_ts, tz=tz)
        target = from_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= from_dt:
            target += timedelta(days=1)
        return int(target.astimezone(timezone.utc).timestamp())
