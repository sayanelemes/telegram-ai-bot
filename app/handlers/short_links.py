import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from app.database.connection import DatabaseManager
from app.keyboards.inline import get_webapp_inline_keyboard

logger = logging.getLogger(__name__)

router = Router(name="short_links_router")


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    await message.answer(
        "📊 <b>Детальная статистика доступна в WebApp:</b>\n\n"
        "Отслеживайте калории, белки, тренировки, динамику веса и расходы.",
        reply_markup=get_webapp_inline_keyboard(text="📊 Открыть статистику", screen="food_stats"),
        parse_mode="HTML"
    )


@router.message(Command("tasks"))
async def cmd_tasks(message: Message):
    await message.answer(
        "📋 <b>Ваши задачи:</b>",
        reply_markup=get_webapp_inline_keyboard(text="📋 Открыть задачи", screen="tasks"),
        parse_mode="HTML"
    )


@router.message(Command("notes"))
async def cmd_notes(message: Message):
    await message.answer(
        "📝 <b>Ваши заметки и идеи:</b>",
        reply_markup=get_webapp_inline_keyboard(text="📝 Открыть заметки", screen="notes"),
        parse_mode="HTML"
    )


@router.message(Command("workout"))
async def cmd_workout(message: Message):
    await message.answer(
        "💪 <b>Тренировочный план и журнал:</b>",
        reply_markup=get_webapp_inline_keyboard(text="💪 Открыть тренировки", screen="workout"),
        parse_mode="HTML"
    )


@router.message(Command("recipe"))
async def cmd_recipe(message: Message):
    await message.answer(
        "🍳 <b>Быстрый рецепт для набора массы:</b>",
        reply_markup=get_webapp_inline_keyboard(text="🍳 Открыть рецепты", screen="recipe"),
        parse_mode="HTML"
    )


@router.message(Command("insights"))
async def cmd_insights(message: Message):
    await message.answer(
        "💡 <b>Аналитика и персональные советы:</b>",
        reply_markup=get_webapp_inline_keyboard(text="💡 Открыть советы", screen="insights"),
        parse_mode="HTML"
    )


@router.message(Command("storage"))
async def cmd_storage(message: Message, db_manager: DatabaseManager):
    stats = await db_manager.get_storage_stats()
    size_mb = stats.get("db_size_mb", 0.0)
    tables = stats.get("tables", {})

    top_tables = sorted(tables.items(), key=lambda x: x[1], reverse=True)[:7]
    tables_text = "\n".join(f"• <code>{t}</code>: {cnt} записей" for t, cnt in top_tables)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧹 Запустить VACUUM и оптимизацию", callback_data="storage_vacuum")],
        [InlineKeyboardButton(text="🚀 Открыть WebApp", web_app=get_webapp_inline_keyboard().inline_keyboard[0][0].web_app)]
    ])

    await message.answer(
        f"💾 <b>Состояние хранилища базы данных:</b>\n\n"
        f"📦 Размер файла БД: <b>{size_mb} МБ</b>\n\n"
        f"<b>Основные таблицы:</b>\n{tables_text}\n\n"
        f"SQLite работает в режиме WAL с индексами для максимальной скорости.",
        reply_markup=kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "storage_vacuum")
async def handle_storage_vacuum(callback: CallbackQuery, db_manager: DatabaseManager):
    await db_manager.optimize_db()
    await db_manager.vacuum_db()
    stats = await db_manager.get_storage_stats()
    await callback.message.edit_text(
        f"✅ <b>База данных успешно оптимизирована!</b>\n"
        f"Новый размер: <b>{stats.get('db_size_mb', 0.0)} МБ</b>",
        parse_mode="HTML"
    )
    await callback.answer()
