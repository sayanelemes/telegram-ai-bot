import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, StorageKey
from aiogram.types import Message, CallbackQuery, User, Chat

from app.handlers.start import (
    handle_start,
    process_gender,
    process_age,
    process_height,
    process_weight,
    process_activity,
    process_goal,
)
from app.handlers.menu import handle_today, handle_my_goal
from app.states.user_states import OnboardingStates
from app.services.reminders import ReminderService


def make_user(telegram_id=12345, first_name="Alex", username="alex_fit"):
    return User(id=telegram_id, is_bot=False, first_name=first_name, username=username)


def make_chat(chat_id=12345):
    return Chat(id=chat_id, type="private")


def make_fsm_context(bot_id=999, chat_id=12345, user_id=12345):
    storage = MemoryStorage()
    key = StorageKey(bot_id=bot_id, chat_id=chat_id, user_id=user_id)
    return FSMContext(storage=storage, key=key)


@pytest.mark.asyncio
async def test_onboarding_and_start_flow(
    user_repo,
    food_repo,
    expense_repo,
    reminder_repo,
    nutrition_service,
    mock_bot,
):
    tg_user = make_user()
    chat = make_chat()
    state = make_fsm_context()
    reminder_service = ReminderService(reminder_repo, bot=mock_bot)

    # 1. New user /start triggers onboarding
    start_message = AsyncMock(spec=Message)
    start_message.from_user = tg_user
    start_message.chat = chat
    start_message.answer = AsyncMock()

    await handle_start(
        start_message,
        state,
        user_repo,
        food_repo,
        expense_repo,
        reminder_service,
    )
    assert await state.get_state() == OnboardingStates.gender.state
    assert start_message.answer.called

    # 2. Process Gender
    callback_gender = AsyncMock(spec=CallbackQuery)
    callback_gender.data = "gender_male"
    callback_gender.from_user = tg_user
    callback_gender.message = AsyncMock()
    callback_gender.message.edit_text = AsyncMock()
    callback_gender.answer = AsyncMock()

    await process_gender(callback_gender, state)
    assert await state.get_state() == OnboardingStates.age.state
    data = await state.get_data()
    assert data["gender"] == "male"

    # 3. Process Age
    age_message = AsyncMock(spec=Message)
    age_message.from_user = tg_user
    age_message.text = "25"
    age_message.answer = AsyncMock()

    await process_age(age_message, state)
    assert await state.get_state() == OnboardingStates.height.state
    data = await state.get_data()
    assert data["age"] == 25

    # 4. Process Height
    height_message = AsyncMock(spec=Message)
    height_message.from_user = tg_user
    height_message.text = "180"
    height_message.answer = AsyncMock()

    await process_height(height_message, state)
    assert await state.get_state() == OnboardingStates.weight.state
    data = await state.get_data()
    assert data["height_cm"] == 180.0

    # 5. Process Weight
    weight_message = AsyncMock(spec=Message)
    weight_message.from_user = tg_user
    weight_message.text = "80"
    weight_message.answer = AsyncMock()

    await process_weight(weight_message, state)
    assert await state.get_state() == OnboardingStates.activity.state
    data = await state.get_data()
    assert data["weight_kg"] == 80.0

    # 6. Process Activity
    callback_activity = AsyncMock(spec=CallbackQuery)
    callback_activity.data = "activity_moderate"
    callback_activity.from_user = tg_user
    callback_activity.message = AsyncMock()
    callback_activity.message.edit_text = AsyncMock()
    callback_activity.answer = AsyncMock()

    await process_activity(callback_activity, state)
    assert await state.get_state() == OnboardingStates.goal.state
    data = await state.get_data()
    assert data["activity_level"] == "moderate"

    # 7. Process Goal
    callback_goal = AsyncMock(spec=CallbackQuery)
    callback_goal.data = "goal_loss"
    callback_goal.from_user = tg_user
    callback_goal.message = AsyncMock()
    callback_goal.message.edit_text = AsyncMock()
    callback_goal.message.answer = AsyncMock()
    callback_goal.answer = AsyncMock()

    await process_goal(
        callback_goal,
        state,
        user_repo,
        nutrition_service,
        reminder_service,
    )
    # State should be cleared
    assert await state.get_state() is None

    # Verify user profile & goal stored in DB
    user = await user_repo.get_by_telegram_id(tg_user.id)
    assert user is not None
    profile = await user_repo.get_profile(user.id)
    assert profile is not None
    assert profile.age == 25
    assert profile.weight_kg == 80.0
    goal = await user_repo.get_calorie_goal(user.id)
    assert goal is not None
    assert goal.target_calories > 0

    # 8. Start again: should now render dashboard without onboarding!
    start_message_2 = AsyncMock(spec=Message)
    start_message_2.from_user = tg_user
    start_message_2.chat = chat
    start_message_2.answer = AsyncMock()

    await handle_start(
        start_message_2,
        state,
        user_repo,
        food_repo,
        expense_repo,
        reminder_service,
    )
    assert await state.get_state() is None
    all_calls_text = " ".join(str(c[0][0]) for c in start_message_2.answer.call_args_list)
    assert "Привет, Alex!" in all_calls_text
    assert "Сегодня" in all_calls_text


@pytest.mark.asyncio
async def test_menu_handlers(user_repo, food_repo, expense_repo):
    user = await user_repo.get_or_create_user(telegram_id=98765, first_name="Sam")
    msg = AsyncMock(spec=Message)
    msg.from_user = make_user(telegram_id=98765, first_name="Sam")
    msg.answer = AsyncMock()

    await handle_today(msg, user_repo, food_repo, expense_repo)
    assert msg.answer.called
    today_text = msg.answer.call_args[0][0]
    assert "Калории" in today_text
    assert "Белки" in today_text
