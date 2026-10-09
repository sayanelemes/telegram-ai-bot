from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from app.database.repositories.user_repository import UserRepository
from app.database.repositories.food_repository import FoodRepository
from app.keyboards.inline import get_history_pagination_keyboard
from app.utils.formatters import format_number

router = Router(name="history_router")

MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
}


def format_russian_date(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{dt.day} {MONTHS_RU.get(dt.month, '')}"
    except Exception:
        return date_str


async def build_history_text(
    user_id: int,
    offset_days: int,
    limit_days: int,
    food_repo: FoodRepository,
    user_repo: UserRepository,
) -> tuple[str, int]:
    total_days = await food_repo.count_history_days(user_id)
    history = await food_repo.get_history_by_dates(user_id, limit_days=limit_days, offset_days=offset_days)
    goal = await user_repo.get_calorie_goal(user_id)

    target_cal = goal.target_calories if goal else 2000
    target_prot = goal.target_protein_g if goal else 150

    if not history:
        return "📅 <i>В дневнике питания пока нет сохранённых записей.</i>", 0

    lines = ["📅 <b>История питания:</b>\n"]
    for idx, day in enumerate(history):
        d_title = format_russian_date(day["date"])
        lines.append(
            f"📅 <b>{d_title}</b> ({day['meals_count']} приёмов пищи)\n\n"
            f"🔥 <b>{format_number(day['calories'])} / {format_number(target_cal)} ккал</b>\n"
            f"🥩 <b>{day['protein']} / {target_prot} г</b> белка\n"
            f"🥑 <b>{day['fat']} г</b> жиров | 🍚 <b>{day['carbs']} г</b> углей\n"
        )
        if idx < len(history) - 1:
            lines.append("━━━━━━━━━━━━\n")

    return "\n".join(lines), total_days


@router.message(F.text == "📅 История")
async def handle_history_menu(
    message: Message,
    user_repo: UserRepository,
    food_repo: FoodRepository,
):
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Пожалуйста, начните с команды /start")
        return

    text, total_days = await build_history_text(
        user_id=user.id,
        offset_days=0,
        limit_days=7,
        food_repo=food_repo,
        user_repo=user_repo,
    )

    markup = get_history_pagination_keyboard(offset_days=0, total_days=total_days, page_size=7)
    await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("history_offset_"))
async def handle_history_page(
    callback: CallbackQuery,
    user_repo: UserRepository,
    food_repo: FoodRepository,
):
    offset = int(callback.data.replace("history_offset_", ""))
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer()
        return

    text, total_days = await build_history_text(
        user_id=user.id,
        offset_days=offset,
        limit_days=7,
        food_repo=food_repo,
        user_repo=user_repo,
    )
    markup = get_history_pagination_keyboard(offset_days=offset, total_days=total_days, page_size=7)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.in_({"history_quick_7", "history_quick_30"}))
async def handle_history_quick(
    callback: CallbackQuery,
    user_repo: UserRepository,
    food_repo: FoodRepository,
):
    limit = 7 if callback.data == "history_quick_7" else 30
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer()
        return

    text, total_days = await build_history_text(
        user_id=user.id,
        offset_days=0,
        limit_days=limit,
        food_repo=food_repo,
        user_repo=user_repo,
    )
    markup = get_history_pagination_keyboard(offset_days=0, total_days=total_days, page_size=limit)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()
