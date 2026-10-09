from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class UserDB(BaseModel):
    id: Optional[int] = None
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    timezone: str = "Asia/Almaty"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class UserProfileDB(BaseModel):
    id: Optional[int] = None
    user_id: int
    gender: str  # 'male' | 'female'
    age: int
    height_cm: float
    weight_kg: float
    activity_level: str  # 'sedentary' | 'light' | 'moderate' | 'high' | 'very_high'
    goal: str  # 'loss' | 'maintain' | 'gain'
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class CalorieGoalDB(BaseModel):
    id: Optional[int] = None
    user_id: int
    bmr: int
    tdee: int
    target_calories: int
    target_protein_g: int
    target_fat_g: int
    target_carbs_g: int
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class FoodItemDB(BaseModel):
    id: Optional[int] = None
    food_entry_id: Optional[int] = None
    name: str
    portion_g: float
    calories: int
    protein_g: float
    fat_g: float
    carbs_g: float


class FoodEntryDB(BaseModel):
    id: Optional[int] = None
    user_id: int
    meal_type: str  # 'breakfast' | 'lunch' | 'dinner' | 'snack' | 'meal'
    entry_date: str  # YYYY-MM-DD
    entry_time: str  # HH:MM
    total_calories: int
    total_protein: float
    total_fat: float
    total_carbs: float
    advice: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    items: List[FoodItemDB] = Field(default_factory=list)


class ExpenseItemDB(BaseModel):
    id: Optional[int] = None
    expense_id: Optional[int] = None
    name: str
    price: float
    quantity: float = 1.0


class ExpenseDB(BaseModel):
    id: Optional[int] = None
    user_id: int
    merchant: str
    amount: float
    currency: str = "₸"
    category: str = "food"  # 'food' | 'transport' | 'shopping' | 'entertainment' | 'utilities' | 'other' | 'salary' | 'income'
    entry_type: str = "expense"  # 'expense' | 'income'
    description: Optional[str] = None
    raw_text: Optional[str] = None
    ai_analysis: Optional[str] = None
    is_impulsive: bool = False
    expense_date: str  # YYYY-MM-DD
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    items: List[ExpenseItemDB] = Field(default_factory=list)


class BudgetDB(BaseModel):
    id: Optional[int] = None
    user_id: int
    weekly_budget: float = 0.0
    monthly_budget: float = 0.0
    currency: str = "₸"
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ReminderDB(BaseModel):
    id: Optional[int] = None
    user_id: int
    reminder_type: str  # 'breakfast' | 'lunch' | 'dinner' | 'water' | 'summary'
    time_str: str  # '09:00' or '2' (for hours)
    interval_hours: int = 0
    is_enabled: bool = True
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class DailyNutritionSummary(BaseModel):
    date: str
    consumed_calories: int = 0
    consumed_protein: float = 0.0
    consumed_fat: float = 0.0
    consumed_carbs: float = 0.0
    target_calories: int = 2000
    target_protein: int = 150
    target_fat: int = 70
    target_carbs: int = 230
    entries_count: int = 0
