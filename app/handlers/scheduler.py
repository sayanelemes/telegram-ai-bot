import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.database.repositories.user_repository import UserRepository
from app.database.repositories.productivity_repository import ProductivityRepository

logger = logging.getLogger(__name__)

router = Router(name="scheduler_router")


@router.callback_query(F.data.startswith("snooze_rem:"))
async def handle_snooze_reminder(
    callback: CallbackQuery,
    user_repo: UserRepository,
    productivity_repo: ProductivityRepository,
):
    parts = callback.data.split(":")
    if len(parts) >= 3:
        minutes = int(parts[1])
        schedule_id = int(parts[2])
        now_ts = int(datetime.utcnow().timestamp())
        await productivity_repo.snooze_schedule(schedule_id, minutes, now_ts)
        await callback.answer(f"⏳ Напоминание отложено на {minutes} мин.")
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer(f"⏳ Отложено на <b>{minutes} мин</b>.", parse_mode="HTML")
        except Exception:
            pass
    else:
        await callback.answer("Ошибка формата snooze")


@router.callback_query(F.data.startswith("snooze_hunger:"))
async def handle_snooze_hunger(callback: CallbackQuery):
    parts = callback.data.split(":")
    minutes = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 30
    await callback.answer(f"⏳ Напомним перекусить через {minutes} мин.")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"⏳ Напоминание о приёме пищи отложено на <b>{minutes} мин</b>.", parse_mode="HTML")
    except Exception:
        pass


@router.callback_query(F.data == "quick_shake")
async def handle_quick_shake_recipe(callback: CallbackQuery):
    await callback.answer("⚡️ Рецепт экспресс-шейка")
    recipe_text = (
        "🥤 <b>Экспресс-шейк для набора массы (550 ккал, 35 г белка)</b>:\n\n"
        "• Молоко 3.2% или соевое — <b>300 мл</b>\n"
        "• Банан — <b>1 шт (~120 г)</b>\n"
        "• Овсяные хлопья — <b>50 г</b>\n"
        "• Арахисовая паста — <b>25 г (1 ст. л.)</b>\n"
        "• Сывороточный протеин — <b>30 г</b> (или 100 г мягкого творога)\n\n"
        "⏱ <i>Всё в блендер на 60 секунд. Пьётся легко за 1 минуту, закрывая дефицит калорий без чувства тяжести!</i>"
    )
    try:
        await callback.message.answer(recipe_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to send shake recipe: {e}")


@router.callback_query(F.data.startswith("satiety:"))
async def handle_satiety_rating(
    callback: CallbackQuery,
    user_repo: UserRepository,
    productivity_repo: ProductivityRepository,
):
    parts = callback.data.split(":")
    rating = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 3

    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if user:
        tz_str = user.timezone or "Asia/Almaty"
        try:
            tz = ZoneInfo(tz_str)
        except Exception:
            tz = ZoneInfo("Asia/Almaty")
        today_str = datetime.now(tz=tz).date().isoformat()

        await productivity_repo.save_check_in(
            user_id=user.id,
            log_date=today_str,
            mood=rating,
            energy=rating,
            satiety=rating,
            notes=f"Оценка из вечернего чекаута: {rating}/5",
        )

    await callback.answer(f"✅ Оценка {rating}/5 сохранена!")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            f"✅ <b>Вечерний чекаут завершён!</b> Оценка сытости и самочувствия: <b>{rating}/5</b>.",
            parse_mode="HTML",
        )
    except Exception:
        pass
