import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app.database.repositories.user_repository import UserRepository
from app.database.repositories.reminder_repository import ReminderRepository
from app.services.reminders import ReminderService
from app.states.user_states import ReminderStates
from app.keyboards.inline import get_reminders_keyboard, get_timezone_keyboard

logger = logging.getLogger(__name__)

router = Router(name="reminders_router")


async def render_reminders_screen(
    user_id: int,
    timezone_str: str,
    reminder_repo: ReminderRepository,
) -> tuple[str, list]:
    reminders = await reminder_repo.get_user_reminders(user_id)
    text = (
        "⏰ <b>Управление напоминаниями</b>\n\n"
        "Настройте удобное расписание уведомлений о приёмах пищи, воде и итогах дня.\n"
        f"🌍 Текущий часовой пояс: <b>{timezone_str}</b>\n\n"
        "Нажмите на напоминание, чтобы <b>включить/выключить</b> его, или ✏️ <b>Время</b>, чтобы изменить час."
    )
    return text, reminders


@router.message(F.text == "⏰ Напоминания")
async def handle_reminders_menu(
    message: Message,
    user_repo: UserRepository,
    reminder_repo: ReminderRepository,
    reminder_service: ReminderService,
):
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Пожалуйста, начните с команды /start")
        return

    # Ensure defaults exist
    await reminder_service.init_default_user_reminders(user.id)
    text, reminders = await render_reminders_screen(user.id, user.timezone, reminder_repo)
    markup = get_reminders_keyboard(reminders)
    await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data == "rem_back")
async def handle_reminders_back(
    callback: CallbackQuery,
    user_repo: UserRepository,
    reminder_repo: ReminderRepository,
):
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer()
        return

    text, reminders = await render_reminders_screen(user.id, user.timezone, reminder_repo)
    markup = get_reminders_keyboard(reminders)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("rem_toggle_"))
async def handle_toggle_reminder(
    callback: CallbackQuery,
    user_repo: UserRepository,
    reminder_repo: ReminderRepository,
    reminder_service: ReminderService,
):
    rem_type = callback.data.replace("rem_toggle_", "")
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer()
        return

    current = await reminder_repo.get_reminder(user.id, rem_type)
    if current:
        new_status = not current.is_enabled
        await reminder_repo.toggle_reminder(user.id, rem_type, new_status)
        current.is_enabled = new_status
        await reminder_service.register_job_for_user(
            user_id=user.id,
            telegram_id=user.telegram_id,
            timezone_str=user.timezone,
            reminder=current
        )

    text, reminders = await render_reminders_screen(user.id, user.timezone, reminder_repo)
    markup = get_reminders_keyboard(reminders)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer(f"Статус обновлён: {'Включено ✅' if current and current.is_enabled else 'Выключено ❌'}")


@router.callback_query(F.data.startswith("rem_edit_"))
async def handle_edit_reminder_time(
    callback: CallbackQuery,
    state: FSMContext,
):
    rem_type = callback.data.replace("rem_edit_", "")
    await state.update_data(editing_rem_type=rem_type)

    if rem_type == "water":
        await state.set_state(ReminderStates.editing_water_interval)
        await callback.message.answer(
            "💧 Введите интервал напоминаний о воде в часах (например: <b>2</b> или <b>3</b>):",
            parse_mode="HTML"
        )
    else:
        await state.set_state(ReminderStates.editing_time)
        await callback.message.answer(
            "⏰ Введите новое время в формате <b>ЧЧ:ММ</b> (например: <b>08:30</b> или <b>13:00</b>):",
            parse_mode="HTML"
        )
    await callback.answer()


@router.message(ReminderStates.editing_time)
async def process_new_time(
    message: Message,
    state: FSMContext,
    user_repo: UserRepository,
    reminder_repo: ReminderRepository,
    reminder_service: ReminderService,
):
    text = (message.text or "").strip()
    # Simple validation of HH:MM
    parts = text.split(":")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await message.answer("⚠️ Неверный формат времени. Введите в формате ЧЧ:ММ (например: 09:00):")
        return

    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        await message.answer("⚠️ Недопустимое время. Часы 0-23, минуты 0-59. Попробуйте снова:")
        return

    formatted_time = f"{hour:02d}:{minute:02d}"
    data = await state.get_data()
    rem_type = data.get("editing_rem_type", "breakfast")
    await state.clear()

    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user:
        return

    await reminder_repo.update_reminder_time(user.id, rem_type, formatted_time, interval_hours=0)
    updated_rem = await reminder_repo.get_reminder(user.id, rem_type)
    if updated_rem:
        await reminder_service.register_job_for_user(
            user_id=user.id,
            telegram_id=user.telegram_id,
            timezone_str=user.timezone,
            reminder=updated_rem
        )

    await message.answer(f"✅ Время напоминания установлено на <b>{formatted_time}</b>", parse_mode="HTML")


@router.message(ReminderStates.editing_water_interval)
async def process_new_water_interval(
    message: Message,
    state: FSMContext,
    user_repo: UserRepository,
    reminder_repo: ReminderRepository,
    reminder_service: ReminderService,
):
    text = (message.text or "").strip()
    if not text.isdigit() or not (1 <= int(text) <= 6):
        await message.answer("⚠️ Введите целое число от 1 до 6 часов:")
        return

    interval = int(text)
    await state.clear()

    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user:
        return

    await reminder_repo.update_reminder_time(user.id, "water", str(interval), interval_hours=interval)
    updated_rem = await reminder_repo.get_reminder(user.id, "water")
    if updated_rem:
        await reminder_service.register_job_for_user(
            user_id=user.id,
            telegram_id=user.telegram_id,
            timezone_str=user.timezone,
            reminder=updated_rem
        )

    await message.answer(f"✅ Интервал напоминания о воде установлен: каждые <b>{interval} ч</b>", parse_mode="HTML")


@router.callback_query(F.data == "rem_timezone")
async def handle_show_timezones(callback: CallbackQuery):
    await callback.message.edit_text(
        "🌍 <b>Выберите ваш часовой пояс:</b>",
        reply_markup=get_timezone_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tz_set_"))
async def handle_set_timezone(
    callback: CallbackQuery,
    user_repo: UserRepository,
    reminder_repo: ReminderRepository,
    reminder_service: ReminderService,
):
    tz_name = callback.data.replace("tz_set_", "")
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer()
        return

    await user_repo.update_timezone(user.id, tz_name)
    user.timezone = tz_name

    # Reschedule all user jobs with new timezone
    user_reminders = await reminder_repo.get_user_reminders(user.id)
    for r in user_reminders:
        await reminder_service.register_job_for_user(
            user_id=user.id,
            telegram_id=user.telegram_id,
            timezone_str=tz_name,
            reminder=r
        )

    text, reminders = await render_reminders_screen(user.id, tz_name, reminder_repo)
    markup = get_reminders_keyboard(reminders)
    await callback.message.edit_text(f"✅ Часовой пояс изменён на <b>{tz_name}</b>\n\n" + text, reply_markup=markup, parse_mode="HTML")
    await callback.answer("Часовой пояс обновлен!")
