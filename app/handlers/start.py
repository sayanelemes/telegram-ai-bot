import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app.database.models import UserProfileDB, CalorieGoalDB
from app.database.repositories.user_repository import UserRepository
from app.database.repositories.food_repository import FoodRepository
from app.database.repositories.expense_repository import ExpenseRepository
from app.services.nutrition import NutritionService
from app.services.reminders import ReminderService
from app.states.user_states import OnboardingStates
from app.keyboards.reply import get_main_menu_keyboard
from app.keyboards.inline import (
    get_gender_keyboard,
    get_activity_keyboard,
    get_goal_keyboard,
    get_webapp_inline_keyboard,
)
from app.utils.formatters import generate_progress_bar, format_currency, format_number
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

router = Router(name="start_router")


async def render_main_dashboard(
    user_id: int,
    telegram_id: int,
    first_name: str,
    timezone_str: str,
    user_repo: UserRepository,
    food_repo: FoodRepository,
    expense_repo: ExpenseRepository,
) -> str:
    """Renders the comprehensive daily progress dashboard (Section 27)."""
    tz = ZoneInfo(timezone_str)
    today_str = datetime.now(tz).strftime("%Y-%m-%d")

    goal = await user_repo.get_calorie_goal(user_id)
    daily_food = await food_repo.get_daily_totals(user_id, today_str)
    daily_expense = await expense_repo.get_daily_total(user_id, today_str)

    target_cal = goal.target_calories if goal else 2000
    target_prot = goal.target_protein_g if goal else 150
    target_fat = goal.target_fat_g if goal else 70
    target_carbs = goal.target_carbs_g if goal else 230

    consumed_cal = daily_food["calories"]
    consumed_prot = daily_food["protein"]
    consumed_fat = daily_food["fat"]
    consumed_carbs = daily_food["carbs"]

    bar = generate_progress_bar(consumed_cal, target_cal)

    text = (
        f"👋 <b>Привет, {first_name or 'друг'}!</b>\n\n"
        f"📊 <b>Сегодня</b>\n\n"
        f"🔥 <b>{format_number(consumed_cal)} / {format_number(target_cal)} ккал</b>\n"
        f"{bar}\n\n"
        f"🥩 Белки: <b>{consumed_prot} / {target_prot} г</b>\n"
        f"🥑 Жиры: <b>{consumed_fat} / {target_fat} г</b>\n"
        f"🍚 Углеводы: <b>{consumed_carbs} / {target_carbs} г</b>\n\n"
        f"💰 Расходы сегодня: <b>{format_currency(daily_expense)}</b>\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"Что хочешь сделать?"
    )
    return text


@router.message(CommandStart())
async def handle_start(
    message: Message,
    state: FSMContext,
    user_repo: UserRepository,
    food_repo: FoodRepository,
    expense_repo: ExpenseRepository,
    reminder_service: ReminderService,
):
    await state.clear()
    user = await user_repo.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    profile = await user_repo.get_profile(user.id)
    if profile:
        # Existing user: show main dashboard
        dashboard_text = await render_main_dashboard(
            user_id=user.id,
            telegram_id=user.telegram_id,
            first_name=user.first_name or "друг",
            timezone_str=user.timezone,
            user_repo=user_repo,
            food_repo=food_repo,
            expense_repo=expense_repo,
        )
        await message.answer(
            dashboard_text,
            reply_markup=get_webapp_inline_keyboard(),
            parse_mode="HTML"
        )
        await message.answer(
            "Главное меню управления:",
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        # New user: start onboarding
        await state.set_state(OnboardingStates.gender)
        welcome_text = (
            f"👋 <b>Добро пожаловать, {message.from_user.first_name or 'друг'}!</b>\n\n"
            "Я — твой персональный AI-помощник по питанию, калориям и расходам.\n"
            "Давай настроим твой профиль для точного расчёта суточной нормы.\n\n"
            "Укажи твой пол:"
        )
        await message.answer(welcome_text, reply_markup=get_gender_keyboard(), parse_mode="HTML")


# --- Onboarding FSM Handlers ---

@router.callback_query(OnboardingStates.gender, F.data.startswith("gender_"))
async def process_gender(callback: CallbackQuery, state: FSMContext):
    gender = "male" if callback.data == "gender_male" else "female"
    await state.update_data(gender=gender)
    await state.set_state(OnboardingStates.age)
    await callback.message.edit_text(
        f"Пол выбран: {'👨 Мужчина' if gender == 'male' else '👩 Женщина'}\n\n"
        "🎂 Введи твой <b>возраст</b> (полных лет):\n<i>Например: 25</i>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(OnboardingStates.age)
async def process_age(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⚠️ Пожалуйста, введи возраст числом (например: 25):")
        return

    age = int(text)
    if not (14 <= age <= 100):
        await message.answer("⚠️ Пожалуйста, укажи реальный возраст от 14 до 100 лет:")
        return

    await state.update_data(age=age)
    await state.set_state(OnboardingStates.height)
    await message.answer(
        "📏 Введи твой <b>рост в сантиметрах</b>:\n<i>Например: 180</i>",
        parse_mode="HTML"
    )


@router.message(OnboardingStates.height)
async def process_height(message: Message, state: FSMContext):
    text = (message.text or "").strip().replace(",", ".")
    try:
        height = float(text)
        if not (100.0 <= height <= 250.0):
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введи корректный рост от 100 до 250 см:")
        return

    await state.update_data(height_cm=height)
    await state.set_state(OnboardingStates.weight)
    await message.answer(
        "⚖️ Введи твой <b>вес в килограммах</b>:\n<i>Например: 80 или 72.5</i>",
        parse_mode="HTML"
    )


@router.message(OnboardingStates.weight)
async def process_weight(message: Message, state: FSMContext):
    text = (message.text or "").strip().replace(",", ".")
    try:
        weight = float(text)
        if not (30.0 <= weight <= 300.0):
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введи реальный вес от 30 до 300 кг:")
        return

    await state.update_data(weight_kg=weight)
    await state.set_state(OnboardingStates.activity)
    await message.answer(
        "🏃 Выбери твой <b>уровень физической активности</b>:",
        reply_markup=get_activity_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(OnboardingStates.activity, F.data.startswith("activity_"))
async def process_activity(callback: CallbackQuery, state: FSMContext):
    activity_level = callback.data.replace("activity_", "")
    await state.update_data(activity_level=activity_level)
    await state.set_state(OnboardingStates.goal)
    await callback.message.edit_text(
        "🎯 Выбери твою <b>основную цель</b>:",
        reply_markup=get_goal_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(OnboardingStates.goal, F.data.startswith("goal_"))
async def process_goal(
    callback: CallbackQuery,
    state: FSMContext,
    user_repo: UserRepository,
    nutrition_service: NutritionService,
    reminder_service: ReminderService,
):
    goal = callback.data.replace("goal_", "")
    data = await state.get_data()
    await state.clear()

    user = await user_repo.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )

    # Validate inputs with service
    validation = nutrition_service.validate_inputs(
        gender=data["gender"],
        age=data["age"],
        height_cm=data["height_cm"],
        weight_kg=data["weight_kg"],
        activity_level=data["activity_level"],
        goal=goal,
    )
    if not validation.is_valid:
        await callback.message.answer(f"❌ Ошибка в данных: {validation.error_message}")
        await callback.answer()
        return

    # Calculate targets
    targets = nutrition_service.calculate_targets(
        gender=data["gender"],
        age=data["age"],
        height_cm=data["height_cm"],
        weight_kg=data["weight_kg"],
        activity_level=data["activity_level"],
        goal=goal,
    )

    # Save profile
    profile = UserProfileDB(
        user_id=user.id,
        gender=data["gender"],
        age=data["age"],
        height_cm=data["height_cm"],
        weight_kg=data["weight_kg"],
        activity_level=data["activity_level"],
        goal=goal,
    )
    await user_repo.save_profile(profile)

    # Save calorie goal
    goal_db = CalorieGoalDB(
        user_id=user.id,
        bmr=targets.bmr,
        tdee=targets.tdee,
        target_calories=targets.target_calories,
        target_protein_g=targets.target_protein_g,
        target_fat_g=targets.target_fat_g,
        target_carbs_g=targets.target_carbs_g,
    )
    await user_repo.save_calorie_goal(goal_db)

    # Initialize default reminders
    await reminder_service.init_default_user_reminders(user.id)
    reminders = await reminder_service.reminder_repo.get_user_reminders(user.id)
    for r in reminders:
        await reminder_service.register_job_for_user(
            user_id=user.id,
            telegram_id=user.telegram_id,
            timezone_str=user.timezone,
            reminder=r,
        )

    goal_titles = {
        "loss": "📉 Похудение",
        "maintain": "⚖️ Поддержание веса",
        "gain": "📈 Набор массы",
    }

    result_text = (
        "🎉 <b>Профиль успешно настроен!</b>\n\n"
        f"🎯 Цель: <b>{goal_titles.get(goal, goal)}</b>\n\n"
        "🔥 <b>Ваша дневная цель:</b>\n\n"
        f"Калории: <b>{format_number(targets.target_calories)} ккал</b>\n\n"
        f"🥩 Белки: <b>{targets.target_protein_g} г</b>\n"
        f"🥑 Жиры: <b>{targets.target_fat_g} г</b>\n"
        f"🍚 Углеводы: <b>{targets.target_carbs_g} г</b>\n\n"
        "━━━━━━━━━━━━━━\n"
        "<i>💡 Примечание: Это ориентировочные значения, рассчитанные по формуле Миффлина-Сан Жеора, а не медицинская рекомендация.</i>"
    )

    await callback.message.edit_text(result_text, parse_mode="HTML")
    await callback.message.answer(
        "Вы можете отправить фото блюда или чека в любой момент!",
        reply_markup=get_main_menu_keyboard(),
    )
    await callback.answer()
