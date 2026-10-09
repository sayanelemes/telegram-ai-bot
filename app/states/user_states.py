from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    gender = State()
    age = State()
    height = State()
    weight = State()
    activity = State()
    goal = State()


class FoodInputStates(StatesGroup):
    waiting_for_food = State()
    confirming_food = State()


class ExpenseInputStates(StatesGroup):
    waiting_for_expense = State()
    confirming_expense = State()


class ProfileEditStates(StatesGroup):
    selecting_field = State()
    editing_weight = State()
    editing_height = State()
    editing_age = State()
    editing_activity = State()
    editing_goal = State()


class ReminderStates(StatesGroup):
    editing_time = State()
    editing_water_interval = State()
    editing_timezone = State()
