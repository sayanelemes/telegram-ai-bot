import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app.database.models import UserProfileDB, CalorieGoalDB
from app.database.repositories.user_repository import UserRepository
from app.services.nutrition import NutritionService
from app.states.user_states import ProfileEditStates
from app.keyboards.inline import (
    get_profile_keyboard,
    get_profile_edit_fields_keyboard,
    get_activity_keyboard,
    get_goal_keyboard,
)
from app.utils.formatters import format_number

logger = logging.getLogger(__name__)

router = Router(name="profile_router")

ACTIVITY_TITLES = {
    "sedentary": "🛋 Минимальная",
    "light": "🚶 Лёгкая",
    "moderate": "🏃 Средняя",
    "high": "🏋️ Высокая",
    "very_high": "🔥 Очень высокая",
}

GOAL_TITLES = {
    "loss": "📉 Похудение",
    "maintain": "⚖️ Поддержание веса",
    "gain": "📈 Набор массы",
}


def build_profile_view_text(profile: UserProfileDB, goal: CalorieGoalDB) -> str:
    gender_str = "Мужчина" if profile.gender == "male" else "Женщина"
    act_str = ACTIVITY_TITLES.get(profile.activity_level, profile.activity_level)
    goal_str = GOAL_TITLES.get(profile.goal, profile.goal)

    text = (
        "👤 <b>Ваш профиль</b>\n\n"
        f"Пол: <b>{gender_str}</b>\n"
        f"Возраст: <b>{profile.age}</b>\n"
        f"Рост: <b>{int(profile.height_cm)} см</b>\n"
        f"Вес: <b>{profile.weight_kg} кг</b>\n\n"
        f"Активность: <b>{act_str}</b>\n"
        f"Цель: <b>{goal_str}</b>\n\n"
        f"🔥 <b>Цель: {format_number(goal.target_calories)} ккал</b>\n\n"
        f"🥩 Белки: <b>{goal.target_protein_g} г</b>\n"
        f"🥑 Жиры: <b>{goal.target_fat_g} г</b>\n"
        f"🍚 Углеводы: <b>{goal.target_carbs_g} г</b>"
    )
    return text


@router.message(F.text == "👤 Профиль")
@router.callback_query(F.data == "profile_view")
async def handle_profile_menu(
    event: Message | CallbackQuery,
    user_repo: UserRepository,
):
    from_user = event.from_user
    user = await user_repo.get_by_telegram_id(from_user.id)
    if not user:
        if isinstance(event, Message):
            await event.answer("Пожалуйста, начните с /start")
        else:
            await event.answer()
        return

    profile = await user_repo.get_profile(user.id)
    goal = await user_repo.get_calorie_goal(user.id)

    if not profile or not goal:
        text = "Профиль ещё не заполнен. Нажмите /start для настройки."
        if isinstance(event, Message):
            await event.answer(text)
        else:
            await event.message.edit_text(text)
            await event.answer()
        return

    text = build_profile_view_text(profile, goal)
    markup = get_profile_keyboard()

    if isinstance(event, Message):
        await event.answer(text, reply_markup=markup, parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await event.answer()


@router.callback_query(F.data == "profile_edit_start")
async def handle_edit_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "✏️ Выберите параметр, который хотите изменить:",
        reply_markup=get_profile_edit_fields_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "edit_field_weight")
async def edit_weight_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProfileEditStates.editing_weight)
    await callback.message.answer("⚖️ Введите ваш новый вес в кг (например: <b>78.5</b>):", parse_mode="HTML")
    await callback.answer()


@router.message(ProfileEditStates.editing_weight)
async def process_new_weight(
    message: Message,
    state: FSMContext,
    user_repo: UserRepository,
    nutrition_service: NutritionService,
):
    text = (message.text or "").strip().replace(",", ".")
    try:
        weight = float(text)
        if not (30.0 <= weight <= 300.0):
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Введите реальный вес от 30 до 300 кг:")
        return

    await state.clear()
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    profile = await user_repo.get_profile(user.id)
    if not profile:
        return

    profile.weight_kg = weight
    await user_repo.save_profile(profile)

    # Recalculate targets
    targets = nutrition_service.calculate_targets(
        gender=profile.gender,
        age=profile.age,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        activity_level=profile.activity_level,
        goal=profile.goal,
    )
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

    text = f"✅ Вес обновлён ({weight} кг) и целевые калории пересчитаны!\n\n" + build_profile_view_text(profile, goal_db)
    await message.answer(text, reply_markup=get_profile_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "edit_field_height")
async def edit_height_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProfileEditStates.editing_height)
    await callback.message.answer("📏 Введите ваш новый рост в см (например: <b>182</b>):", parse_mode="HTML")
    await callback.answer()


@router.message(ProfileEditStates.editing_height)
async def process_new_height(
    message: Message,
    state: FSMContext,
    user_repo: UserRepository,
    nutrition_service: NutritionService,
):
    text = (message.text or "").strip().replace(",", ".")
    try:
        height = float(text)
        if not (100.0 <= height <= 250.0):
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Введите реальный рост от 100 до 250 см:")
        return

    await state.clear()
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    profile = await user_repo.get_profile(user.id)
    if not profile:
        return

    profile.height_cm = height
    await user_repo.save_profile(profile)

    targets = nutrition_service.calculate_targets(
        gender=profile.gender,
        age=profile.age,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        activity_level=profile.activity_level,
        goal=profile.goal,
    )
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

    text = f"✅ Рост обновлён ({height} см)!\n\n" + build_profile_view_text(profile, goal_db)
    await message.answer(text, reply_markup=get_profile_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "edit_field_age")
async def edit_age_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProfileEditStates.editing_age)
    await callback.message.answer("🎂 Введите ваш возраст (например: <b>26</b>):", parse_mode="HTML")
    await callback.answer()


@router.message(ProfileEditStates.editing_age)
async def process_new_age(
    message: Message,
    state: FSMContext,
    user_repo: UserRepository,
    nutrition_service: NutritionService,
):
    text = (message.text or "").strip()
    if not text.isdigit() or not (14 <= int(text) <= 100):
        await message.answer("⚠️ Введите возраст от 14 до 100:")
        return

    age = int(text)
    await state.clear()
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    profile = await user_repo.get_profile(user.id)
    if not profile:
        return

    profile.age = age
    await user_repo.save_profile(profile)

    targets = nutrition_service.calculate_targets(
        gender=profile.gender,
        age=profile.age,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        activity_level=profile.activity_level,
        goal=profile.goal,
    )
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

    text = f"✅ Возраст обновлён ({age} лет)!\n\n" + build_profile_view_text(profile, goal_db)
    await message.answer(text, reply_markup=get_profile_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "edit_field_activity")
async def edit_activity_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProfileEditStates.editing_activity)
    await callback.message.edit_text("🏃 Выберите новый уровень активности:", reply_markup=get_activity_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(ProfileEditStates.editing_activity, F.data.startswith("activity_"))
async def process_new_activity(
    callback: CallbackQuery,
    state: FSMContext,
    user_repo: UserRepository,
    nutrition_service: NutritionService,
):
    act = callback.data.replace("activity_", "")
    await state.clear()

    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    profile = await user_repo.get_profile(user.id)
    if not profile:
        await callback.answer()
        return

    profile.activity_level = act
    await user_repo.save_profile(profile)

    targets = nutrition_service.calculate_targets(
        gender=profile.gender,
        age=profile.age,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        activity_level=profile.activity_level,
        goal=profile.goal,
    )
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

    text = f"✅ Активность обновлена!\n\n" + build_profile_view_text(profile, goal_db)
    await callback.message.edit_text(text, reply_markup=get_profile_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "edit_field_goal")
async def edit_goal_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProfileEditStates.editing_goal)
    await callback.message.edit_text("🎯 Выберите новую цель:", reply_markup=get_goal_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(ProfileEditStates.editing_goal, F.data.startswith("goal_"))
async def process_new_goal(
    callback: CallbackQuery,
    state: FSMContext,
    user_repo: UserRepository,
    nutrition_service: NutritionService,
):
    goal_name = callback.data.replace("goal_", "")
    await state.clear()

    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    profile = await user_repo.get_profile(user.id)
    if not profile:
        await callback.answer()
        return

    profile.goal = goal_name
    await user_repo.save_profile(profile)

    targets = nutrition_service.calculate_targets(
        gender=profile.gender,
        age=profile.age,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        activity_level=profile.activity_level,
        goal=profile.goal,
    )
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

    text = f"✅ Цель обновлена!\n\n" + build_profile_view_text(profile, goal_db)
    await callback.message.edit_text(text, reply_markup=get_profile_keyboard(), parse_mode="HTML")
    await callback.answer()
