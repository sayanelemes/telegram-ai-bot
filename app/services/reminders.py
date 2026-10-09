import logging
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from aiogram import Bot

from app.database.repositories.reminder_repository import ReminderRepository
from app.database.models import ReminderDB

logger = logging.getLogger(__name__)


class ReminderService:
    REMINDER_MESSAGES = {
        "breakfast": "🍳 Доброе утро! Время полезного завтрака. Не забудь сфотографировать или записать свой приём пищи 🥪",
        "lunch": "🍲 Время вкусного обеда! Не забудь сфотографировать или записать своё блюдо в дневник 🥗",
        "dinner": "🍽 Время ужина! Поддержи баланс белков и овощей и не забудь записать еду 🥩🥦",
        "water": "💧 Напоминание: выпей стакан чистой воды! Водный баланс необходим для здоровья и энергии 🥤",
        "summary": "📊 Пора подвести итоги дня! Открой раздел «Сегодня», чтобы проверить выполнение нормы калорий и расходы 🎯",
    }

    REMINDER_TITLES = {
        "breakfast": "🍳 Завтрак",
        "lunch": "🍲 Обед",
        "dinner": "🍽 Ужин",
        "water": "💧 Вода",
        "summary": "📊 Итоги дня",
    }

    DEFAULT_REMINDERS = [
        {"reminder_type": "breakfast", "time_str": "09:00", "interval_hours": 0, "is_enabled": True},
        {"reminder_type": "lunch", "time_str": "13:00", "interval_hours": 0, "is_enabled": True},
        {"reminder_type": "dinner", "time_str": "19:00", "interval_hours": 0, "is_enabled": True},
        {"reminder_type": "water", "time_str": "2", "interval_hours": 2, "is_enabled": True},
        {"reminder_type": "summary", "time_str": "21:00", "interval_hours": 0, "is_enabled": True},
    ]

    def __init__(self, reminder_repo: ReminderRepository, bot: Optional[Bot] = None):
        self.reminder_repo = reminder_repo
        self.bot = bot
        self.scheduler = AsyncIOScheduler()

    def set_bot(self, bot: Bot) -> None:
        self.bot = bot

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Reminder scheduler started.")

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Reminder scheduler stopped.")

    def _get_job_id(self, user_id: int, reminder_type: str) -> str:
        return f"reminder_{user_id}_{reminder_type}"

    async def init_default_user_reminders(self, user_id: int) -> None:
        """Create standard reminders for a newly registered user if not exist."""
        existing = await self.reminder_repo.get_user_reminders(user_id)
        if not existing:
            for item in self.DEFAULT_REMINDERS:
                reminder = ReminderDB(
                    user_id=user_id,
                    reminder_type=item["reminder_type"],
                    time_str=item["time_str"],
                    interval_hours=item["interval_hours"],
                    is_enabled=item["is_enabled"]
                )
                await self.reminder_repo.save_reminder(reminder)

    async def register_job_for_user(
        self,
        user_id: int,
        telegram_id: int,
        timezone_str: str,
        reminder: ReminderDB
    ) -> None:
        """Add or update an APScheduler job for a specific user reminder."""
        job_id = self._get_job_id(user_id, reminder.reminder_type)

        # Remove existing job if any
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        if not reminder.is_enabled:
            return

        try:
            tz = ZoneInfo(timezone_str)
        except (ZoneInfoNotFoundError, Exception):
            tz = ZoneInfo("Asia/Almaty")

        if reminder.reminder_type == "water":
            # Interval trigger during waking hours (e.g. every N hours between 09:00 and 21:00)
            hours = reminder.interval_hours if reminder.interval_hours > 0 else 2
            # Run every N hours using cron or interval
            trigger = CronTrigger(
                hour=f"9-21/{hours}",
                minute="0",
                timezone=tz
            )
        else:
            # Parse HH:MM
            try:
                parts = reminder.time_str.split(":")
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
            except Exception:
                hour, minute = 12, 0

            trigger = CronTrigger(hour=hour, minute=minute, timezone=tz)

        self.scheduler.add_job(
            func=self._send_reminder_message,
            trigger=trigger,
            id=job_id,
            name=f"User {telegram_id} {reminder.reminder_type}",
            args=[telegram_id, reminder.reminder_type],
            replace_existing=True,
            misfire_grace_time=3600
        )
        logger.debug(f"Scheduled job {job_id} for user {telegram_id} at {reminder.time_str} ({timezone_str})")

    async def _send_reminder_message(self, telegram_id: int, reminder_type: str) -> None:
        """Scheduled task callback: sends notification to user via Telegram."""
        if not self.bot:
            logger.warning(f"Cannot send reminder: Bot instance is not set.")
            return

        message_text = self.REMINDER_MESSAGES.get(
            reminder_type,
            "⏰ Напоминание от вашего AI-помощника по питанию!"
        )

        try:
            await self.bot.send_message(chat_id=telegram_id, text=message_text)
            logger.info(f"Sent {reminder_type} reminder to {telegram_id}")
        except Exception as e:
            logger.error(f"Failed to send reminder to {telegram_id}: {e}")

    async def sync_all_jobs(self) -> None:
        """Load all active reminders from database and register jobs in APScheduler."""
        active_list = await self.reminder_repo.get_all_active_reminders()
        logger.info(f"Syncing {len(active_list)} active reminders with scheduler.")
        for item in active_list:
            reminder = ReminderDB(
                id=item["id"],
                user_id=item["user_id"],
                reminder_type=item["reminder_type"],
                time_str=item["time_str"],
                interval_hours=item["interval_hours"],
                is_enabled=True,
            )
            await self.register_job_for_user(
                user_id=item["user_id"],
                telegram_id=item["telegram_id"],
                timezone_str=item["timezone"] or "Asia/Almaty",
                reminder=reminder
            )
