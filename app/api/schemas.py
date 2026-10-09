from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    id: int
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    timezone: str


class MacroItem(BaseModel):
    goal: int
    consumed: float


class MacrosSummary(BaseModel):
    protein: MacroItem
    fat: MacroItem
    carbs: MacroItem


class CalorieSummary(BaseModel):
    goal: int
    consumed: int
    remaining: int
    exceeded: int
    percentage: int


class FoodItemSchema(BaseModel):
    id: Optional[int] = None
    name: str
    portion_g: float
    calories: int
    protein_g: float
    fat_g: float
    carbs_g: float


class FoodEntryResponse(BaseModel):
    id: int
    meal_type: str
    entry_date: str
    entry_time: str
    total_calories: int
    total_protein: float
    total_fat: float
    total_carbs: float
    advice: Optional[str] = None
    items: List[FoodItemSchema] = Field(default_factory=list)


class DashboardResponse(BaseModel):
    user_name: str
    timezone: str
    calories: CalorieSummary
    macros: MacrosSummary
    meals: List[FoodEntryResponse]
    today_expenses: float
    is_profile_configured: bool


class FoodTextAnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, description="Описание блюда")


class FoodSaveRequest(BaseModel):
    meal_name: Optional[str] = "Приём пищи"
    meal_type: Optional[str] = None  # if not provided, auto-detected from current time
    total_calories: int
    total_protein: float
    total_fat: float
    total_carbs: float
    advice: Optional[str] = None
    items: List[FoodItemSchema]


class ExpenseItemSchema(BaseModel):
    id: Optional[int] = None
    name: str
    price: float
    quantity: float = 1.0


class ExpenseEntryResponse(BaseModel):
    id: int
    merchant: str
    amount: float
    currency: str
    category: str
    category_label: str
    entry_type: str = "expense"
    is_impulsive: bool = False
    ai_analysis: Optional[str] = None
    description: Optional[str] = None
    expense_date: str
    items: List[ExpenseItemSchema] = Field(default_factory=list)


class CategoryExpenseSummary(BaseModel):
    category: str
    label: str
    total: float
    count: int


class BudgetSchema(BaseModel):
    weekly_budget: float = 0.0
    monthly_budget: float = 0.0
    week_spent: float = 0.0
    month_spent: float = 0.0
    week_remaining: float = 0.0
    month_remaining: float = 0.0
    week_exceeded: float = 0.0
    month_exceeded: float = 0.0
    week_percentage: float = 0.0
    month_percentage: float = 0.0
    currency: str = "₸"


class BudgetUpdateRequest(BaseModel):
    weekly_budget: float = Field(ge=0.0)
    monthly_budget: float = Field(ge=0.0)


class ExpensesSummaryResponse(BaseModel):
    today_total: float
    week_total: float
    month_total: float
    month_income: float = 0.0
    net_balance: float = 0.0
    month_title: str
    categories: List[CategoryExpenseSummary]
    recent: List[ExpenseEntryResponse]
    budget: Optional[BudgetSchema] = None


class ExpenseTextAnalyzeRequest(BaseModel):
    text: str = Field(min_length=1)


class ExpenseSaveRequest(BaseModel):
    merchant: str
    amount: float
    currency: str = "₸"
    category: str = "food"
    entry_type: str = "expense"
    is_impulsive: bool = False
    ai_analysis: Optional[str] = None
    description: Optional[str] = None
    raw_text: Optional[str] = None
    items: List[ExpenseItemSchema] = Field(default_factory=list)


class ProfileResponse(BaseModel):
    gender: Optional[str] = None
    age: Optional[int] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    activity_level: Optional[str] = None
    goal: Optional[str] = None
    bmr: Optional[int] = None
    tdee: Optional[int] = None
    target_calories: Optional[int] = None
    target_protein_g: Optional[int] = None
    target_fat_g: Optional[int] = None
    target_carbs_g: Optional[int] = None
    timezone: str


class ProfileUpdateRequest(BaseModel):
    gender: str
    age: int
    height_cm: float
    weight_kg: float
    activity_level: str
    goal: str


class ReminderItemResponse(BaseModel):
    reminder_type: str
    title: str
    time_str: str
    interval_hours: int
    is_enabled: bool


class ReminderUpdateRequest(BaseModel):
    time_str: Optional[str] = None
    interval_hours: Optional[int] = None
    is_enabled: Optional[bool] = None


class TimezoneUpdateRequest(BaseModel):
    timezone: str


class HistoryDayResponse(BaseModel):
    date: str
    meals_count: int
    calories: int
    protein: float
    fat: float
    carbs: float
    target_calories: int
    percentage: int
