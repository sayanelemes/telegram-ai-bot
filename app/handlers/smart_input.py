import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.database.repositories.user_repository import UserRepository
from app.services.smart_input import SmartInputService
from app.services.gemini import GeminiServiceError, GeminiService
from app.database.connection import DatabaseManager
from app.keyboards.inline import get_webapp_inline_keyboard

logger = logging.getLogger(__name__)

# This router MUST be registered LAST in all_routers to avoid intercepting commands or FSM states!
router = Router(name="smart_input_chat_router")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_free_text_chat_input(
    message: Message,
    state: FSMContext,
    user_repo: UserRepository,
    db_manager: DatabaseManager,
    gemini_service: GeminiService,
):
    # 1. Do not intercept if user is currently inside an active FSM state
    current_state = await state.get_state()
    if current_state is not None:
        return

    user = await user_repo.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    smart_service = SmartInputService(db_manager=db_manager, gemini_service=gemini_service)

    try:
        outcome = await smart_service.execute_input(
            text=message.text,
            user_id=user.id,
            timezone_str=user.timezone or "Asia/Almaty"
        )
    except GeminiServiceError as ge:
        logger.warning(f"Gemini error during chat smart input: {ge}")
        await message.answer(
            f"⚠️ Сервис AI временно недоступен ({ge}). Ничего не было записано.",
            parse_mode="HTML"
        )
        return
    except Exception as e:
        logger.error(f"Unexpected error in chat smart input: {e}", exc_info=True)
        await message.answer(
            "⚠️ Произошла ошибка при обработке сообщения. Данные не были сохранены.",
            parse_mode="HTML"
        )
        return

    # 2. Handlers for outcomes
    if outcome.action == "saved":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="↩️ Отменить", callback_data=f"undo_{outcome.link_id}"),
                InlineKeyboardButton(text="🚀 Приложение", web_app=get_webapp_inline_keyboard().inline_keyboard[0][0].web_app),
            ]
        ])
        await message.answer(outcome.message, reply_markup=kb)

    elif outcome.action == "fast_path":
        await message.answer(outcome.message)

    elif outcome.action == "preview":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Сохранить", callback_data=f"confirm_preview_{outcome.link_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_preview"),
            ],
            [
                InlineKeyboardButton(text="🚀 Открыть в WebApp", web_app=get_webapp_inline_keyboard().inline_keyboard[0][0].web_app)
            ]
        ])
        desc = outcome.message
        if outcome.raw_result and outcome.raw_result.clarification_needed:
            desc += f"\n❓ <i>{outcome.raw_result.clarification_needed}</i>"
        await message.answer(desc, reply_markup=kb, parse_mode="HTML")

    elif outcome.action == "ignored":
        # Polite fallback for greetings or non-actionable text
        await message.answer(
            outcome.message,
            reply_markup=get_webapp_inline_keyboard(text="🚀 Открыть приложение")
        )


@router.callback_query(F.data.startswith("undo_"))
async def handle_undo_callback(
    callback: CallbackQuery,
    user_repo: UserRepository,
    db_manager: DatabaseManager,
    gemini_service: GeminiService,
):
    link_id = callback.data.replace("undo_", "")
    user = await user_repo.get_or_create_user(telegram_id=callback.from_user.id)
    smart_service = SmartInputService(db_manager=db_manager, gemini_service=gemini_service)

    success = await smart_service.undo_by_link_id(link_id=link_id, user_id=user.id)
    if success:
        await callback.message.edit_text("↩️ <b>Запись успешно отменена и удалена.</b>", parse_mode="HTML")
    else:
        await callback.message.answer("⚠️ Не удалось отменить запись или она уже была удалена.")
    await callback.answer()


@router.callback_query(F.data == "cancel_preview")
async def handle_cancel_preview(callback: CallbackQuery):
    await callback.message.edit_text("❌ Запись отменена.")
    await callback.answer()
