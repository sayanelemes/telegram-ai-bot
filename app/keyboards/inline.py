from typing import List, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.config.settings import settings


def get_webapp_inline_keyboard() -> Optional[InlineKeyboardMarkup]:
    # Telegram strictly requires HTTPS for WebAppInfo buttons
    if not settings.WEB_APP_URL or not settings.WEB_APP_URL.startswith("https://"):
        return None

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🍎 Открыть приложение",
            web_app=WebAppInfo(url=settings.WEB_APP_URL)
        )
    )
    return builder.as_markup()


def get_gender_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👨 Мужчина", callback_data="gender_male"),
        InlineKeyboardButton(text="👩 Женщина", callback_data="gender_female"),
    )
    return builder.as_markup()


def get_activity_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🛋 Минимальная", callback_data="activity_sedentary"))
    builder.row(InlineKeyboardButton(text="🚶 Лёгкая", callback_data="activity_light"))
    builder.row(InlineKeyboardButton(text="🏃 Средняя", callback_data="activity_moderate"))
    builder.row(InlineKeyboardButton(text="🏋️ Высокая", callback_data="activity_high"))
    builder.row(InlineKeyboardButton(text="🔥 Очень высокая", callback_data="activity_very_high"))
    return builder.as_markup()


def get_goal_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📉 Похудение", callback_data="goal_loss"))
    builder.row(InlineKeyboardButton(text="⚖️ Поддержание веса", callback_data="goal_maintain"))
    builder.row(InlineKeyboardButton(text="📈 Набор массы", callback_data="goal_gain"))
    return builder.as_markup()


def get_food_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, сохранить", callback_data="confirm_food_save"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="confirm_food_cancel"),
    )
    return builder.as_markup()


def get_expense_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Сохранить", callback_data="confirm_expense_save"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="confirm_expense_cancel"),
    )
    return builder.as_markup()


def get_meal_details_keyboard(entries: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for entry in entries:
        label = f"🔍 {entry.entry_time} — {entry.meal_type.capitalize()} ({entry.total_calories} ккал)"
        builder.row(InlineKeyboardButton(text=label, callback_data=f"meal_detail_{entry.id}"))
    return builder.as_markup()


def get_history_pagination_keyboard(
    offset_days: int,
    total_days: int,
    page_size: int = 7
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    nav_buttons = []
    if offset_days > 0:
        prev_offset = max(0, offset_days - page_size)
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"history_offset_{prev_offset}"))
    if offset_days + page_size < total_days:
        next_offset = offset_days + page_size
        nav_buttons.append(InlineKeyboardButton(text="➡️ Вперёд", callback_data=f"history_offset_{next_offset}"))

    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(
        InlineKeyboardButton(text="📅 Последние 7 дней", callback_data="history_quick_7"),
        InlineKeyboardButton(text="📅 Последние 30 дней", callback_data="history_quick_30"),
    )
    return builder.as_markup()


def get_reminders_keyboard(reminders: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    titles = {
        "breakfast": "🍳 Завтрак",
        "lunch": "🍲 Обед",
        "dinner": "🍽 Ужин",
        "water": "💧 Вода",
        "summary": "📊 Итоги дня",
    }

    for r in reminders:
        title = titles.get(r.reminder_type, r.reminder_type)
        status_icon = "✅" if r.is_enabled else "❌"
        time_display = f"каждые {r.interval_hours} ч" if r.reminder_type == "water" else r.time_str

        # Row with toggle and edit time button
        builder.row(
            InlineKeyboardButton(
                text=f"{status_icon} {title} ({time_display})",
                callback_data=f"rem_toggle_{r.reminder_type}"
            ),
            InlineKeyboardButton(
                text="✏️ Время",
                callback_data=f"rem_edit_{r.reminder_type}"
            )
        )

    builder.row(
        InlineKeyboardButton(text="🌍 Часовой пояс", callback_data="rem_timezone"),
    )
    return builder.as_markup()


def get_timezone_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    timezones = [
        ("🇰🇿 Алматы (UTC+5)", "Asia/Almaty"),
        ("🇷🇺 Москва (UTC+3)", "Europe/Moscow"),
        ("🇺🇿 Ташкент (UTC+5)", "Asia/Tashkent"),
        ("🇰🇬 Бишкек (UTC+6)", "Asia/Bishkek"),
        ("🇬🇪 Тбилиси (UTC+4)", "Asia/Tbilisi"),
        ("🇦🇪 Дубай (UTC+4)", "Asia/Dubai"),
        ("🇪🇺 Берлин (UTC+1)", "Europe/Berlin"),
        ("🌐 UTC (UTC+0)", "UTC"),
    ]
    for label, tz_name in timezones:
        builder.row(InlineKeyboardButton(text=label, callback_data=f"tz_set_{tz_name}"))
    builder.row(InlineKeyboardButton(text="🔙 Назад к напоминаниям", callback_data="rem_back"))
    return builder.as_markup()


def get_profile_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✏️ Изменить данные", callback_data="profile_edit_start"),
    )
    return builder.as_markup()


def get_profile_edit_fields_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⚖️ Вес", callback_data="edit_field_weight"),
        InlineKeyboardButton(text="📏 Рост", callback_data="edit_field_height"),
    )
    builder.row(
        InlineKeyboardButton(text="🎂 Возраст", callback_data="edit_field_age"),
        InlineKeyboardButton(text="🏃 Активность", callback_data="edit_field_activity"),
    )
    builder.row(
        InlineKeyboardButton(text="🎯 Цель", callback_data="edit_field_goal"),
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Назад в профиль", callback_data="profile_view"),
    )
    return builder.as_markup()
