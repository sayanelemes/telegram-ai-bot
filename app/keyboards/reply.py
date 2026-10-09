from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from app.config.settings import settings


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Production main menu keyboard designed for mobile Telegram with Web App."""
    keyboard = []
    if settings.WEB_APP_URL and settings.WEB_APP_URL.startswith("https://"):
        keyboard.append([
            KeyboardButton(text="🍎 Открыть приложение", web_app=WebAppInfo(url=settings.WEB_APP_URL)),
        ])
    keyboard.extend([
        [
            KeyboardButton(text="🍔 Добавить еду"),
            KeyboardButton(text="📷 Анализ фото"),
        ],
        [
            KeyboardButton(text="📊 Сегодня"),
            KeyboardButton(text="📅 История"),
        ],
        [
            KeyboardButton(text="💰 Расходы"),
            KeyboardButton(text="🎯 Моя цель"),
        ],
        [
            KeyboardButton(text="⏰ Напоминания"),
            KeyboardButton(text="👤 Профиль"),
        ],
    ])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите действие или отправьте фото/текст"
    )


def get_cancel_reply_keyboard() -> ReplyKeyboardMarkup:
    """Cancel action reply keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
