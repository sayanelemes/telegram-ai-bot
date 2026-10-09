import io
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app.database.models import FoodEntryDB, FoodItemDB
from app.database.repositories.user_repository import UserRepository
from app.database.repositories.food_repository import FoodRepository
from app.services.gemini import GeminiService, GeminiServiceError, FoodAnalysisResult
from app.services.image import ImageProcessingService, InvalidImageError
from app.states.user_states import FoodInputStates
from app.keyboards.reply import get_main_menu_keyboard, get_cancel_reply_keyboard
from app.keyboards.inline import get_food_confirm_keyboard
from app.utils.formatters import generate_progress_bar, format_number
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = Router(name="food_router")


def format_food_analysis_text(result: FoodAnalysisResult) -> str:
    lines = ["🍽 <b>Анализ еды</b>\n"]
    for item in result.items:
        lines.append(
            f"▫️ <b>{item.name}</b> — ~{int(item.portion_g)} г\n"
            f"🔥 {item.calories} ккал\n"
            f"🥩 Белки: {item.protein_g} г\n"
            f"🥑 Жиры: {item.fat_g} г\n"
            f"🍚 Углеводы: {item.carbs_g} г\n"
        )
    lines.append("━━━━━━━━━━━━━━\n")
    lines.append(
        f"🔥 <b>Всего: {result.total_calories} ккал</b>\n"
        f"🥩 <b>Белки</b>: {result.total_protein} г\n"
        f"🥑 <b>Жиры</b>: {result.total_fat} г\n"
        f"🍚 <b>Углеводы</b>: {result.total_carbs} г\n"
    )
    if result.advice:
        lines.append(f"💡 <b>Совет</b>\n{result.advice}\n")
    lines.append("━━━━━━━━━━━━━━\nСохранить в дневник?")
    return "\n".join(lines)


@router.message(F.text.in_({"🍔 Добавить еду", "📷 Анализ фото"}))
async def prompt_food_input(message: Message, state: FSMContext):
    await state.set_state(FoodInputStates.waiting_for_food)
    await message.answer(
        "📷 Отправьте <b>фотографию вашего блюда</b>\n"
        "или напишите текстом, что вы съели (например: <i>«2 варёных яйца и тост с авокадо»</i>):",
        reply_markup=get_cancel_reply_keyboard(),
        parse_mode="HTML"
    )


@router.message(FoodInputStates.waiting_for_food, F.photo)
@router.message(F.photo & ~F.caption.startswith("/receipt") & ~F.caption.startswith("чек"))
async def handle_food_photo(
    message: Message,
    state: FSMContext,
    bot: Bot,
    gemini_service: GeminiService,
    user_repo: UserRepository,
    food_repo: FoodRepository,
):
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Пожалуйста, начните с команды /start")
        return

    status_msg = await message.answer("🔎 <i>Анализирую вашу еду с помощью Gemini...</i>", parse_mode="HTML")

    try:
        # Download photo into memory
        photo = message.photo[-1]
        buffer = io.BytesIO()
        await bot.download(photo, destination=buffer)
        image_bytes = buffer.getvalue()

        # Validate and optimize image with Pillow
        processed_bytes, mime_type = ImageProcessingService.process_image(
            image_bytes,
            max_size_bytes=settings.max_image_bytes
        )

        # Call Gemini Vision
        analysis = await gemini_service.analyze_food(processed_bytes, mime_type)

        # Save to state data for confirmation
        await state.update_data(
            pending_food=analysis.model_dump(),
            timestamp=datetime.utcnow().isoformat()
        )
        await state.set_state(FoodInputStates.confirming_food)

        await status_msg.delete()
        text = format_food_analysis_text(analysis)
        await message.answer(
            text,
            reply_markup=get_food_confirm_keyboard(),
            parse_mode="HTML"
        )

    except InvalidImageError as e:
        await status_msg.edit_text(f"❌ {e}")
    except GeminiServiceError as e:
        await status_msg.edit_text(f"❌ {e}")
    except Exception as e:
        logger.error(f"Unexpected error in food photo handler: {e}", exc_info=True)
        await status_msg.edit_text("❌ Не удалось проанализировать фото блюда. Попробуйте сделать более чёткий снимок.")


@router.message(FoodInputStates.waiting_for_food, F.text & (F.text != "❌ Отмена"))
async def handle_food_text(
    message: Message,
    state: FSMContext,
    gemini_service: GeminiService,
    user_repo: UserRepository,
):
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Пожалуйста, начните с команды /start")
        return

    status_msg = await message.answer("🔎 <i>Определяю состав и калорийность...</i>", parse_mode="HTML")

    try:
        analysis = await gemini_service.analyze_food_text(message.text)
        await state.update_data(
            pending_food=analysis.model_dump(),
            timestamp=datetime.utcnow().isoformat()
        )
        await state.set_state(FoodInputStates.confirming_food)

        await status_msg.delete()
        text = format_food_analysis_text(analysis)
        await message.answer(
            text,
            reply_markup=get_food_confirm_keyboard(),
            parse_mode="HTML"
        )
    except GeminiServiceError as e:
        await status_msg.edit_text(f"❌ {e}")
    except Exception as e:
        logger.error(f"Error analyzing food text: {e}", exc_info=True)
        await status_msg.edit_text("❌ Не удалось распознать приём пищи. Попробуйте описать подробнее.")


@router.callback_query(FoodInputStates.confirming_food, F.data == "confirm_food_save")
async def save_food_entry(
    callback: CallbackQuery,
    state: FSMContext,
    user_repo: UserRepository,
    food_repo: FoodRepository,
):
    data = await state.get_data()
    pending_dict = data.get("pending_food")
    await state.clear()

    if not pending_dict:
        await callback.message.edit_text("Данные устарели. Попробуйте снова.")
        await callback.answer()
        return

    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.message.edit_text("Пользователь не найден.")
        await callback.answer()
        return

    tz = ZoneInfo(user.timezone)
    now_local = datetime.now(tz)
    today_str = now_local.strftime("%Y-%m-%d")
    time_str = now_local.strftime("%H:%M")

    # Determine meal type by hour
    hour = now_local.hour
    if 5 <= hour < 11:
        meal_type = "Завтрак"
    elif 11 <= hour < 16:
        meal_type = "Обед"
    elif 16 <= hour < 22:
        meal_type = "Ужин"
    else:
        meal_type = "Перекус"

    # Build DB entity
    items_db = [
        FoodItemDB(
            name=it["name"],
            portion_g=it["portion_g"],
            calories=it["calories"],
            protein_g=it["protein_g"],
            fat_g=it["fat_g"],
            carbs_g=it["carbs_g"],
        )
        for it in pending_dict.get("items", [])
    ]

    entry = FoodEntryDB(
        user_id=user.id,
        meal_type=meal_type,
        entry_date=today_str,
        entry_time=time_str,
        total_calories=pending_dict["total_calories"],
        total_protein=pending_dict["total_protein"],
        total_fat=pending_dict["total_fat"],
        total_carbs=pending_dict["total_carbs"],
        advice=pending_dict.get("advice"),
        items=items_db,
    )

    await food_repo.create_food_entry(entry)

    # Show updated progress for today (Section 5)
    goal = await user_repo.get_calorie_goal(user.id)
    daily_food = await food_repo.get_daily_totals(user.id, today_str)

    target_cal = goal.target_calories if goal else 2000
    target_prot = goal.target_protein_g if goal else 150
    target_fat = goal.target_fat_g if goal else 70
    target_carbs = goal.target_carbs_g if goal else 230

    consumed_cal = daily_food["calories"]
    consumed_prot = daily_food["protein"]
    consumed_fat = daily_food["fat"]
    consumed_carbs = daily_food["carbs"]

    bar = generate_progress_bar(consumed_cal, target_cal)

    updated_text = (
        "✅ <b>Блюдо успешно сохранено в дневник!</b>\n\n"
        "🔥 <b>Сегодня:</b>\n\n"
        f"<b>{format_number(consumed_cal)} / {format_number(target_cal)} ккал</b>\n\n"
        f"{bar}\n\n"
        f"🥩 <b>Белки</b>\n{consumed_prot} / {target_prot} г\n\n"
        f"🥑 <b>Жиры</b>\n{consumed_fat} / {target_fat} г\n\n"
        f"🍚 <b>Углеводы</b>\n{consumed_carbs} / {target_carbs} г"
    )

    await callback.message.edit_text(updated_text, parse_mode="HTML")
    await callback.message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())
    await callback.answer()


@router.callback_query(FoodInputStates.confirming_food, F.data == "confirm_food_cancel")
async def cancel_food_save(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Добавление еды отменено.")
    await callback.message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())
    await callback.answer()
