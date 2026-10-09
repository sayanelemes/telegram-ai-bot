import {
  DashboardData,
  FoodEntry,
  FoodAnalysisResult,
  HistoryDay,
  ExpensesSummary,
  ReceiptAnalysisResult,
  ExpenseParsedResult,
  ExpenseEntry,
  ProfileData,
  ReminderItem,
} from './types';

const API_BASE = '/api';

// Extract and persist standalone token from URL if present
try {
  const urlParams = new URLSearchParams(window.location.search);
  const tokenFromUrl = urlParams.get('token');
  if (tokenFromUrl) {
    localStorage.setItem('auth_token', tokenFromUrl);
    // Remove token from address bar for cleanliness
    urlParams.delete('token');
    const newSearch = urlParams.toString();
    const newUrl = window.location.pathname + (newSearch ? '?' + newSearch : '');
    window.history.replaceState({}, '', newUrl);
  }
} catch (e) {
  console.debug('Token parsing notice:', e);
}

function getAuthHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    'Accept': 'application/json',
  };

  // 1. Check standalone persistent token
  let authToken = '';
  try {
    authToken = localStorage.getItem('auth_token') || '';
  } catch {}

  // 2. Check Telegram WebApp initData
  let initData = window.Telegram?.WebApp?.initData || '';
  if (initData) {
    try {
      localStorage.setItem('tg_init_data', initData);
    } catch {}
  } else {
    try {
      initData = localStorage.getItem('tg_init_data') || '';
    } catch {}
  }

  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
    headers['X-Auth-Token'] = authToken;
  } else if (initData) {
    headers['Authorization'] = `tma ${initData}`;
    headers['X-Telegram-Init-Data'] = initData;
  }

  return headers;
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const headers = {
    ...getAuthHeaders(),
    ...(options.headers || {}),
  };

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorDetail = 'Произошла ошибка при выполнении запроса';
    try {
      const errJson = await response.json();
      if (errJson.detail) {
        errorDetail = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {
      errorDetail = response.statusText;
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

export const api = {
  // Dashboard
  getDashboard: () => request<DashboardData>('/dashboard'),

  // Food
  getTodayFood: () => request<FoodEntry[]>('/food/today'),

  analyzeFoodPhoto: async (file: File): Promise<FoodAnalysisResult> => {
    const formData = new FormData();
    formData.append('file', file);
    const headers = getAuthHeaders() as Record<string, string>;

    const response = await fetch(`${API_BASE}/food/analyze/photo`, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Ошибка анализа фото' }));
      throw new Error(err.detail || 'Не удалось распознать фото блюда');
    }
    return response.json();
  },

  analyzeFoodText: (text: string) =>
    request<FoodAnalysisResult>('/food/analyze/text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }),

  saveFood: (data: any) =>
    request<FoodEntry>('/food', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  deleteFood: (id: number) =>
    request<{ success: boolean }>(`/food/${id}`, {
      method: 'DELETE',
    }),

  // History
  getHistory: (limit = 14, offset = 0) =>
    request<HistoryDay[]>(`/history?limit=${limit}&offset=${offset}`),

  getHistoryByDate: (date: string) =>
    request<FoodEntry[]>(`/history/${date}`),

  // Expenses
  getExpenses: () => request<ExpensesSummary>('/expenses'),

  analyzeReceiptPhoto: async (file: File): Promise<ReceiptAnalysisResult> => {
    const formData = new FormData();
    formData.append('file', file);
    const headers = getAuthHeaders() as Record<string, string>;

    const response = await fetch(`${API_BASE}/expenses/analyze/photo`, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Ошибка анализа чека' }));
      throw new Error(err.detail || 'Не удалось распознать чек');
    }
    return response.json();
  },

  analyzeExpenseText: (text: string) =>
    request<ExpenseParsedResult>('/expenses/analyze/text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }),

  saveExpense: (data: any) =>
    request<ExpenseEntry>('/expenses', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  deleteExpense: (id: number) =>
    request<{ success: boolean }>(`/expenses/${id}`, {
      method: 'DELETE',
    }),

  getBudget: () => request<BudgetSummary>('/expenses/budget'),

  updateBudget: (weekly_budget: number, monthly_budget: number) =>
    request<BudgetSummary>('/expenses/budget', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ weekly_budget, monthly_budget }),
    }),

  // Profile
  getProfile: () => request<ProfileData>('/profile'),

  updateProfile: (data: any) =>
    request<ProfileData>('/profile', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  // Reminders
  getReminders: () => request<ReminderItem[]>('/reminders'),

  updateReminder: (type: string, data: any) =>
    request<ReminderItem>(`/reminders/${type}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  updateTimezone: (timezone: string) =>
    request<{ success: boolean; timezone: string }>('/reminders/timezone', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ timezone }),
    }),

  // Auth methods
  loginWithCode: async (code: string) => {
    const res = await request<{ success: boolean; token: string; user: any }>('/auth/code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    });
    if (res.token) {
      localStorage.setItem('auth_token', res.token);
    }
    return res;
  },

  getAuthToken: async () => {
    const res = await request<{ token: string }>('/auth/token');
    if (res.token) {
      localStorage.setItem('auth_token', res.token);
    }
    return res;
  },
};

