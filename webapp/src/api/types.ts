export interface CalorieSummary {
  goal: number;
  consumed: number;
  remaining: number;
  exceeded: number;
  percentage: number;
}

export interface MacroItem {
  goal: number;
  consumed: number;
}

export interface MacrosSummary {
  protein: MacroItem;
  fat: MacroItem;
  carbs: MacroItem;
}

export interface FoodItem {
  id?: number;
  name: string;
  portion_g: number;
  calories: number;
  protein_g: number;
  fat_g: number;
  carbs_g: number;
}

export interface FoodEntry {
  id: number;
  meal_type: string;
  entry_date: string;
  entry_time: string;
  total_calories: number;
  total_protein: number;
  total_fat: number;
  total_carbs: number;
  advice?: string;
  items: FoodItem[];
}

export interface DashboardData {
  user_name: string;
  timezone: string;
  calories: CalorieSummary;
  macros: MacrosSummary;
  meals: FoodEntry[];
  today_expenses: number;
  is_profile_configured: boolean;
}

export interface FoodAnalysisIngredient {
  name: string;
  portion_g: number;
  calories: number;
  protein_g: number;
  fat_g: number;
  carbs_g: number;
}

export interface FoodAnalysisResult {
  meal_name: string;
  items: FoodAnalysisIngredient[];
  total_calories: number;
  total_protein: number;
  total_fat: number;
  total_carbs: number;
  advice?: string;
}

export interface HistoryDay {
  date: string;
  meals_count: number;
  calories: number;
  protein: number;
  fat: number;
  carbs: number;
  target_calories: number;
  percentage: number;
}

export interface ExpenseItem {
  id?: number;
  name: string;
  price: number;
  quantity: number;
}

export interface BudgetSummary {
  weekly_budget: number;
  monthly_budget: number;
  week_spent: number;
  month_spent: number;
  week_remaining: number;
  month_remaining: number;
  week_exceeded: number;
  month_exceeded: number;
  week_percentage: number;
  month_percentage: number;
  currency: string;
}

export interface ExpenseEntry {
  id: number;
  merchant: string;
  amount: number;
  currency: string;
  category: string;
  category_label: string;
  entry_type?: 'expense' | 'income';
  is_impulsive?: boolean;
  ai_analysis?: string;
  description?: string;
  expense_date: string;
  items: ExpenseItem[];
}

export interface CategorySummary {
  category: string;
  label: string;
  total: number;
  count: number;
}

export interface ExpensesSummary {
  today_total: number;
  week_total: number;
  month_total: number;
  month_income: number;
  net_balance: number;
  month_title: string;
  categories: CategorySummary[];
  recent: ExpenseEntry[];
  budget?: BudgetSummary;
}

export interface ReceiptAnalysisResult {
  merchant: string;
  date?: string;
  currency: string;
  category: string;
  entry_type?: 'expense' | 'income';
  is_impulsive?: boolean;
  ai_analysis?: string;
  items: { name: string; price: number; quantity: number }[];
  total_amount: number;
}

export interface ExpenseParsedResult {
  merchant: string;
  amount: number;
  currency: string;
  category: string;
  entry_type?: 'expense' | 'income';
  is_impulsive?: boolean;
  ai_analysis?: string;
  description?: string;
  items: { name: string; price: number; quantity: number }[];
}

export interface ProfileData {
  gender?: string;
  age?: number;
  height_cm?: number;
  weight_kg?: number;
  activity_level?: string;
  goal?: string;
  bmr?: number;
  tdee?: number;
  target_calories?: number;
  target_protein_g?: number;
  target_fat_g?: number;
  target_carbs_g?: number;
  timezone: string;
}

export interface ReminderItem {
  reminder_type: string;
  title: string;
  time_str: string;
  interval_hours: number;
  is_enabled: boolean;
}
