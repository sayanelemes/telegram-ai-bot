from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.database.repositories.user_repository import UserRepository
from app.database.repositories.food_repository import FoodRepository
from app.database.repositories.expense_repository import ExpenseRepository
from app.keyboards.reply import get_main_menu_keyboard
from app.keyboards.inline import get_meal_details_keyboard
from app.utils.formatters import generate_progress_bar, format_number, format_currency
from app.handlers.start import render_main_dashboard
from app.config.settings import settings
from app.api.auth import create_auth_token, create_login_code

router = Router(name="menu_router")


@router.message(F.text == "❌ Отмена")
async def handle_cancel_text(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Действие отменено.",
        reply_markup=get_main_menu_keyboard()
    )


@router.message(F.text == "📊 Сегодня")
async def handle_today(
    message: Message,
    user_repo: UserRepository,
    food_repo: FoodRepository,
    expense_repo: ExpenseRepository,
):
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Пожалуйста, нажмите /start для начала работы.")
        return

    tz = ZoneInfo(user.timezone)
    today_str = datetime.now(tz).strftime("%Y-%m-%d")

    goal = await user_repo.get_calorie_goal(user.id)
    daily_food = await food_repo.get_daily_totals(user.id, today_str)
    entries = await food_repo.get_entries_by_date(user.id, today_str)

    target_cal = goal.target_calories if goal else 2000
    target_prot = goal.target_protein_g if goal else 150
    target_fat = goal.target_fat_g if goal else 70
    target_carbs = goal.target_carbs_g if goal else 230

    consumed_cal = daily_food["calories"]
    consumed_prot = daily_food["protein"]
    consumed_fat = daily_food["fat"]
    consumed_carbs = daily_food["carbs"]

    bar = generate_progress_bar(consumed_cal, target_cal)

    text_parts = [
        "📊 <b>Сегодня</b>\n",
        f"🔥 <b>Калории</b>\n{format_number(consumed_cal)} / {format_number(target_cal)} ккал\n{bar}\n",
        f"🥩 <b>Белки</b>: {consumed_prot} / {target_prot} г",
        f"🥑 <b>Жиры</b>: {consumed_fat} / {target_fat} г",
        f"🍚 <b>Углеводы</b>: {consumed_carbs} / {target_carbs} г\n",
        "━━━━━━━━━━━━\n",
    ]

    if entries:
        text_parts.append("🍽 <b>Приёмы пищи:</b>\n")
        for e in entries:
            text_parts.append(f"⏱ <b>{e.entry_time}</b> — {e.meal_type.capitalize()}\n🔥 {e.total_calories} ккал\n")
        markup = get_meal_details_keyboard(entries)
    else:
        text_parts.append("🍽 <i>Приёмов пищи пока не записано за сегодня.</i>\nОтправьте фото еды или напишите, что съели!")
        markup = None

    await message.answer("".join(text_parts), reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("meal_detail_"))
async def handle_meal_detail(
    callback: CallbackQuery,
    food_repo: FoodRepository,
):
    entry_id = int(callback.data.replace("meal_detail_", ""))
    entry = await food_repo.get_entry_by_id(entry_id)

    if not entry:
        await callback.answer("Приём пищи не найден.", show_alert=True)
        return

    text_lines = [
        f"🍽 <b>Детали приёма пищи</b> ({entry.entry_time})\n",
        f"Тип: <b>{entry.meal_type.capitalize()}</b>",
        f"🔥 Всего: <b>{entry.total_calories} ккал</b>",
        f"🥩 Б: {entry.total_protein} г | 🥑 Ж: {entry.total_fat} г | 🍚 У: {entry.total_carbs} г\n",
        "<b>Продукты:</b>"
    ]

    for it in entry.items:
        text_lines.append(
            f"• <b>{it.name}</b> (~{int(it.portion_g)} г) — {it.calories} ккал "
            f"(Б: {it.protein_g}г, Ж: {it.fat_g}г, У: {it.carbs_g}г)"
        )

    if entry.advice:
        text_lines.append(f"\n💡 <b>Совет AI:</b>\n{entry.advice}")

    await callback.message.answer("\n".join(text_lines), parse_mode="HTML")
    await callback.answer()


@router.message(F.text == "🎯 Моя цель")
async def handle_my_goal(
    message: Message,
    user_repo: UserRepository,
):
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Пожалуйста, начните с команды /start")
        return

    profile = await user_repo.get_profile(user.id)
    goal = await user_repo.get_calorie_goal(user.id)

    if not profile or not goal:
        await message.answer("Профиль ещё не заполнен. Нажмите /start для настройки.")
        return

    goal_titles = {
        "loss": "📉 Похудение",
        "maintain": "⚖️ Поддержание веса",
        "gain": "📈 Набор массы",
    }

    text = (
        "🎯 <b>Ваша текущая цель и параметры</b>\n\n"
        f"Направление: <b>{goal_titles.get(profile.goal, profile.goal)}</b>\n\n"
        f"🔥 Базовый метаболизм (BMR): <b>{format_number(goal.bmr)} ккал</b>\n"
        f"⚡️ Расход с учётом активности (TDEE): <b>{format_number(goal.tdee)} ккал</b>\n\n"
        f"🎯 <b>Целевая суточная норма:</b>\n"
        f"🔥 Калории: <b>{format_number(goal.target_calories)} ккал</b>\n\n"
        f"🍚 Углеводы: <b>{goal.target_carbs_g} г</b>\n\n"
        "━━━━━━━━━━━━━━\n"
        "Изменить параметры можно в разделе 👤 <b>Профиль</b>."
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command(commands=["ios", "install", "pwa", "app"]))
@router.message(F.text.in_({"📱 На экран iPhone", "📲 На экран iPhone"}))
async def handle_ios_install(message: Message):
    base_url = (settings.WEB_APP_URL or f"http://{settings.API_HOST}:{settings.API_PORT}").rstrip("/")
    token = create_auth_token(message.from_user.id)
    auth_url = f"{base_url}/?token={token}"
    code = create_login_code(message.from_user.id)
    formatted_code = f"{code[:3]} {code[3:]}"

    text = (
        '📱 <b>Как добавить приложение на рабочий стол iPhone:</b>\n\n'
        '1️⃣ Нажмите кнопку <b>«🌐 Открыть в Safari»</b> ниже.\n'
        '2️⃣ В нижней панели Safari нажмите значок <b>⎋ («Поделиться»)</b>.\n'
        '3️⃣ В меню прокрутите вниз и выберите <b>«На экран „Домой“» ⊞</b>.\n'
        '4️⃣ Нажмите <b>«Добавить»</b> в правом верхнем углу.\n\n'
        '✨ <i>Авторизация уже включена в ссылку! Приложение откроется сразу в вашем аккаунте.</i>\n\n'
        f'🔑 Если приложение на рабочем столе запросит код, введите: <code>{formatted_code}</code>'
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🌐 Открыть в Safari (с автовходом)", url=auth_url)
            ]
        ]
    )
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(Command(commands=["code", "login"]))
@router.message(F.text.in_({"🔑 Код для входа", "Код для входа"}))
async def handle_get_login_code(message: Message):
    code = create_login_code(message.from_user.id)
    formatted_code = f"{code[:3]} {code[3:]}"
    base_url = (settings.WEB_APP_URL or f"http://{settings.API_HOST}:{settings.API_PORT}").rstrip("/")
    token = create_auth_token(message.from_user.id)
    auth_url = f"{base_url}/?token={token}"

    text = (
        '🔑 <b>Ваш код для входа на iPhone:</b>\n\n'
        f'<code>{formatted_code}</code>\n\n'
        '⏳ Код действует 30 минут.\n'
        'Введите эти 6 цифр на экране приложения на вашем iPhone.\n\n'
        '💡 <i>Или просто нажмите кнопку ниже для мгновенного входа:</i>'
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚀 Войти автоматически", url=auth_url)
            ]
        ]
    )
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

