import io
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app.database.models import ExpenseDB, ExpenseItemDB
from app.database.repositories.user_repository import UserRepository
from app.database.repositories.expense_repository import ExpenseRepository
from app.services.gemini import GeminiService, GeminiServiceError, ReceiptAnalysisResult, ExpenseParsedResult
from app.services.image import ImageProcessingService, InvalidImageError
from app.services.expenses import ExpenseService
from app.states.user_states import ExpenseInputStates
from app.keyboards.inline import get_expense_confirm_keyboard
from app.utils.formatters import format_currency, format_number
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = Router(name="expenses_router")


def format_receipt_text(res: ReceiptAnalysisResult) -> str:
    lines = [
        "💰 <b>Расход</b>\n",
        f"🏪 <b>{res.merchant}</b>",
    ]
    if res.date:
        lines.append(f"📅 {res.date}")
    lines.append("")

    if res.items:
        for it in res.items:
            qty_str = f" x{it.quantity}" if it.quantity != 1.0 else ""
            lines.append(f"• {it.name}{qty_str} — {format_number(it.price)} {res.currency}")
    else:
        lines.append("• Покупки по чеку")

    lines.append("━━━━━━━━━━━━\n")
    lines.append(f"💰 <b>Итого: {format_currency(res.total_amount, res.currency)}</b>\n")
    lines.append("Сохранить расход?")
    return "\n".join(lines)


def format_parsed_expense_text(res: ExpenseParsedResult) -> str:
    is_income = res.entry_type == "income"
    header = "🟢 <b>Доход</b>" if is_income else "🔴 <b>Расход</b>"
    lines = [
        f"{header}\n",
        f"🏷 <b>{res.merchant}</b>",
        f"📂 Категория: <b>{ExpenseService.get_category_name(res.category)}</b>",
    ]
    if res.description:
        lines.append(f"📝 Описание: {res.description}")

    if res.is_impulsive and not is_income:
        lines.append("\n⚠️ <b>AI: Импульсивная покупка! Не рекомендуется для бюджета.</b>")
    elif res.ai_analysis:
        lines.append(f"\n💡 <b>AI:</b> {res.ai_analysis}")

    lines.append("")
    if res.items and len(res.items) > 1:
        for it in res.items:
            lines.append(f"• {it.name} — {format_number(it.price)} {res.currency}")
        lines.append("━━━━━━━━━━━━")

    sign = "+" if is_income else ""
    lines.append(f"💰 <b>Итого: {sign}{format_currency(res.amount, res.currency)}</b>\n")
    lines.append(f"Сохранить { 'доход' if is_income else 'расход' }?")
    return "\n".join(lines)


@router.message(F.text.in_({"💰 Расходы", "💰 Финансы", "💰 Финансы и расходы"}))
async def handle_expenses_menu(
    message: Message,
    user_repo: UserRepository,
    expense_repo: ExpenseRepository,
):
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Пожалуйста, начните с команды /start")
        return

    expense_service = ExpenseService(expense_repo)
    stats = await expense_service.get_expense_statistics(user.id, user.timezone)

    balance_color = "+" if stats["net_balance"] >= 0 else ""
    lines = [
        f"💳 <b>Финансы за {stats['month_title']}</b>\n",
        f"🔴 Расходы (месяц): <b>{format_currency(stats['month_total'])}</b>",
        f"🟢 Доходы (месяц): <b>+{format_currency(stats['month_income'])}</b>",
        f"⚖️ Баланс: <b>{balance_color}{format_currency(stats['net_balance'])}</b>\n",
        f"📅 Сегодня расходы: <b>{format_currency(stats['today_total'])}</b>",
        f"🗓 За 7 дней: <b>{format_currency(stats['week_total'])}</b>\n",
        "━━━━━━━━━━━━━━\n",
    ]

    budget = stats.get("budget")
    if budget and (budget["weekly_budget"] > 0 or budget["monthly_budget"] > 0):
        lines.append("🎯 <b>Бюджет:</b>")
        if budget["weekly_budget"] > 0:
            lines.append(f"• Неделя: {format_currency(budget['week_spent'])} / {format_currency(budget['weekly_budget'])} ({budget['week_percentage']}%)")
        if budget["monthly_budget"] > 0:
            lines.append(f"• Месяц: {format_currency(budget['month_spent'])} / {format_currency(budget['monthly_budget'])} ({budget['month_percentage']}%)")
        lines.append("\n━━━━━━━━━━━━━━\n")

    if stats["categories"]:
        lines.append("📊 <b>Расходы по категориям:</b>")
        for cat in stats["categories"]:
            lines.append(f"{cat['label']} — <b>{format_currency(cat['total'])}</b>")
        lines.append("\n━━━━━━━━━━━━━━\n")

    lines.append(
        "💡 <b>Как добавить расход или доход:</b>\n"
        "• Отправьте <b>фото чека</b> 🧾\n"
        "• Напишите текстом расход: <i>«кофе 1200 тг»</i> или <i>«такси 2500 тг»</i>\n"
        "• Напишите текстом доход: <i>«зарплата 450000 тг»</i> или <i>«доход фриланс 80000 тг»</i>\n"
        "• Или откройте <b>Telegram Mini App</b> (кнопка внизу) для удобного ввода в 1 клик!"
    )

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(F.caption.startswith("чек") | F.caption.startswith("/receipt") | F.caption.contains("чек"))
@router.message(ExpenseInputStates.waiting_for_expense, F.photo)
async def handle_receipt_photo(
    message: Message,
    state: FSMContext,
    bot: Bot,
    gemini_service: GeminiService,
    user_repo: UserRepository,
):
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Пожалуйста, начните с команды /start")
        return

    status_msg = await message.answer("🔎 <i>Анализирую чек с помощью Gemini...</i>", parse_mode="HTML")

    try:
        photo = message.photo[-1]
        buffer = io.BytesIO()
        await bot.download(photo, destination=buffer)
        image_bytes = buffer.getvalue()

        processed_bytes, mime_type = ImageProcessingService.process_image(
            image_bytes,
            max_size_bytes=settings.max_image_bytes
        )

        receipt_analysis = await gemini_service.analyze_receipt(processed_bytes, mime_type)

        await state.update_data(
            pending_expense=receipt_analysis.model_dump(),
            is_receipt=True,
        )
        await state.set_state(ExpenseInputStates.confirming_expense)

        await status_msg.delete()
        text = format_receipt_text(receipt_analysis)
        await message.answer(text, reply_markup=get_expense_confirm_keyboard(), parse_mode="HTML")

    except InvalidImageError as e:
        await status_msg.edit_text(f"❌ {e}")
    except GeminiServiceError as e:
        await status_msg.edit_text(f"❌ {e}\n\nПопробуйте отправить более чёткое фото чека.")
    except Exception as e:
        logger.error(f"Error analyzing receipt: {e}", exc_info=True)
        await status_msg.edit_text("❌ Не удалось распознать чек. Попробуйте отправить более чёткое фото.")


@router.message(
    F.text.regexp(r"(?i).*\b(тг|тенге|руб|рубл|usd|\$|kzt|rub|\d+\s*(?:тг|₸|₽|\$))\b.*")
    & ~F.text.in_({"💰 Расходы", "🍔 Добавить еду", "📷 Анализ фото", "📊 Сегодня", "📅 История", "🎯 Моя цель", "⏰ Напоминания", "👤 Профиль", "❌ Отмена"})
)
async def handle_expense_text(
    message: Message,
    state: FSMContext,
    gemini_service: GeminiService,
    user_repo: UserRepository,
):
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Пожалуйста, начните с команды /start")
        return

    status_msg = await message.answer("🔎 <i>Распознаю данные о расходе...</i>", parse_mode="HTML")

    try:
        parsed = await gemini_service.parse_expense(message.text)
        await state.update_data(
            pending_expense=parsed.model_dump(),
            is_receipt=False,
            raw_text=message.text,
        )
        await state.set_state(ExpenseInputStates.confirming_expense)

        await status_msg.delete()
        text = format_parsed_expense_text(parsed)
        await message.answer(text, reply_markup=get_expense_confirm_keyboard(), parse_mode="HTML")

    except GeminiServiceError as e:
        await status_msg.edit_text(f"❌ {e}")
    except Exception as e:
        logger.error(f"Error parsing expense text: {e}", exc_info=True)
        await status_msg.edit_text("❌ Не удалось распознать расход. Попробуйте написать понятнее, например: «такси 1500 тг».")


@router.callback_query(ExpenseInputStates.confirming_expense, F.data == "confirm_expense_save")
async def save_expense(
    callback: CallbackQuery,
    state: FSMContext,
    user_repo: UserRepository,
    expense_repo: ExpenseRepository,
):
    data = await state.get_data()
    pending = data.get("pending_expense")
    is_receipt = data.get("is_receipt", False)
    raw_text = data.get("raw_text")
    await state.clear()

    if not pending:
        await callback.message.edit_text("Данные устарели.")
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

    amount = pending.get("total_amount") if is_receipt else pending.get("amount", 0.0)
    merchant = pending.get("merchant", "Покупка")
    currency = pending.get("currency", "₸")
    category = pending.get("category", "food")
    description = pending.get("description")

    items_list = []
    for it in pending.get("items", []):
        items_list.append(ExpenseItemDB(
            name=it.get("name", "Товар"),
            price=float(it.get("price", 0.0)),
            quantity=float(it.get("quantity", 1.0)),
        ))

    entry_type = pending.get("entry_type", "expense")
    is_impulsive = bool(pending.get("is_impulsive", False))
    ai_analysis = pending.get("ai_analysis")

    expense = ExpenseDB(
        user_id=user.id,
        merchant=merchant,
        amount=float(amount),
        currency=currency,
        category=category,
        entry_type=entry_type,
        is_impulsive=is_impulsive,
        ai_analysis=ai_analysis,
        description=description,
        raw_text=raw_text,
        expense_date=today_str,
        items=items_list,
    )

    await expense_repo.create_expense(expense)

    if entry_type == "income":
        confirm_msg = (
            "✅ <b>Доход успешно зафиксирован!</b>\n\n"
            f"💰 {merchant}: <b>+{format_currency(amount, currency)}</b>\n"
            f"📂 Категория: <b>{ExpenseService.get_category_name(category)}</b>\n"
        )
    else:
        today_total = await expense_repo.get_daily_total(user.id, today_str)
        impulsive_line = "\n⚠️ <b>AI: Импульсивная покупка! Не рекомендуется для бюджета.</b>\n" if is_impulsive else ""
        confirm_msg = (
            "✅ <b>Расход успешно сохранён!</b>\n\n"
            f"🏪 {merchant}: <b>{format_currency(amount, currency)}</b>\n"
            f"📂 Категория: <b>{ExpenseService.get_category_name(category)}</b>"
            f"{impulsive_line}\n\n"
            f"💰 Всего расходов за сегодня: <b>{format_currency(today_total, currency)}</b>"
        )

    await callback.message.edit_text(confirm_msg, parse_mode="HTML")
    await callback.answer()


@router.callback_query(ExpenseInputStates.confirming_expense, F.data == "confirm_expense_cancel")
async def cancel_expense(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Добавление расхода отменено.")
    await callback.answer()
