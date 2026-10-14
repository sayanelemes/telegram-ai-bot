import logging
from pathlib import Path
from typing import AsyncGenerator, Dict, Any, List
from contextlib import asynccontextmanager
import aiosqlite

logger = logging.getLogger(__name__)

CREATE_TABLES_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    timezone TEXT NOT NULL DEFAULT 'Asia/Almaty',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    gender TEXT NOT NULL,
    age INTEGER NOT NULL,
    height_cm REAL NOT NULL,
    weight_kg REAL NOT NULL,
    activity_level TEXT NOT NULL,
    goal TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS calorie_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    bmr INTEGER NOT NULL,
    tdee INTEGER NOT NULL,
    target_calories INTEGER NOT NULL,
    target_protein_g INTEGER NOT NULL,
    target_fat_g INTEGER NOT NULL,
    target_carbs_g INTEGER NOT NULL,
    training_surplus_pct INTEGER DEFAULT 10,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS food_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    meal_type TEXT NOT NULL,
    entry_date TEXT NOT NULL,
    entry_time TEXT NOT NULL,
    total_calories INTEGER NOT NULL,
    total_protein REAL NOT NULL,
    total_fat REAL NOT NULL,
    total_carbs REAL NOT NULL,
    advice TEXT,
    link_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS food_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    food_entry_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    portion_g REAL NOT NULL,
    calories INTEGER NOT NULL,
    protein_g REAL NOT NULL,
    fat_g REAL NOT NULL,
    carbs_g REAL NOT NULL,
    FOREIGN KEY (food_entry_id) REFERENCES food_entries (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    merchant TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT '₸',
    category TEXT NOT NULL DEFAULT 'food',
    entry_type TEXT NOT NULL DEFAULT 'expense',
    description TEXT,
    raw_text TEXT,
    ai_analysis TEXT,
    is_impulsive INTEGER DEFAULT 0,
    is_impulse INTEGER DEFAULT 0,
    impulse_reason TEXT,
    link_id TEXT,
    source TEXT DEFAULT 'manual',
    expense_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS expense_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    quantity REAL NOT NULL DEFAULT 1.0,
    FOREIGN KEY (expense_id) REFERENCES expenses (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    reminder_type TEXT NOT NULL,
    time_str TEXT NOT NULL,
    interval_hours INTEGER DEFAULT 0,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, reminder_type),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    weekly_budget REAL DEFAULT 0.0,
    monthly_budget REAL DEFAULT 0.0,
    currency TEXT NOT NULL DEFAULT '₸',
    impulse_monthly_limit REAL DEFAULT 0.0,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS category_budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    monthly_limit REAL NOT NULL,
    alert_80_sent INTEGER DEFAULT 0,
    alert_100_sent INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, category),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    job_type TEXT NOT NULL,
    target_id INTEGER,
    scheduled_time TEXT NOT NULL,
    next_run_at INTEGER NOT NULL,
    days_of_week TEXT DEFAULT 'all',
    data_json TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS gemini_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    call_date TEXT NOT NULL,
    call_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(user_id, call_date),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS custom_foods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    calories_per_100g INTEGER NOT NULL,
    protein_per_100g REAL NOT NULL,
    fat_per_100g REAL NOT NULL,
    carbs_per_100g REAL NOT NULL,
    is_favorite INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pantry_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    amount_str TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS water_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount_ml INTEGER NOT NULL,
    log_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS weight_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    weight_kg REAL NOT NULL,
    log_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS supplements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    dosage TEXT NOT NULL,
    schedule_time TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS supplement_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplement_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    taken_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (supplement_id) REFERENCES supplements (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    due_at TEXT,
    priority TEXT DEFAULT 'normal',
    repeat TEXT DEFAULT 'none',
    is_completed INTEGER DEFAULT 0,
    postponed_count INTEGER DEFAULT 0,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    tags TEXT,
    is_pinned INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    target_frequency TEXT DEFAULT 'daily',
    streak INTEGER DEFAULT 0,
    best_streak INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS habit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    habit_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    log_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(habit_id, log_date),
    FOREIGN KEY (habit_id) REFERENCES habits (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS check_ins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    log_date TEXT NOT NULL,
    mood INTEGER NOT NULL,
    energy INTEGER NOT NULL,
    satiety INTEGER DEFAULT 3,
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, log_date),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    target_value REAL NOT NULL,
    current_value REAL NOT NULL,
    unit TEXT NOT NULL DEFAULT 'kg',
    target_date TEXT,
    is_completed INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS workout_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    days_per_week INTEGER DEFAULT 4,
    plan_data_json TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS workout_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    workout_date TEXT NOT NULL,
    exercise_name TEXT NOT NULL,
    weight_kg REAL NOT NULL,
    reps INTEGER NOT NULL,
    sets INTEGER NOT NULL,
    rpe REAL,
    is_pr INTEGER DEFAULT 0,
    raw_text TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS savings_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    target_amount REAL NOT NULL,
    current_amount REAL DEFAULT 0.0,
    monthly_deposit REAL DEFAULT 0.0,
    currency TEXT DEFAULT '₸',
    target_date TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT DEFAULT '₸',
    billing_cycle TEXT DEFAULT 'monthly',
    next_payment_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS debts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    person_name TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT DEFAULT '₸',
    direction TEXT NOT NULL,
    description TEXT,
    is_settled INTEGER DEFAULT 0,
    settled_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_modes (
    user_id INTEGER PRIMARY KEY,
    do_not_disturb_until TEXT,
    sick_mode_until TEXT,
    travel_mode_until TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS last_recipes (
    user_id INTEGER PRIMARY KEY,
    recipe_json TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS shopping_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    amount_str TEXT,
    category TEXT DEFAULT 'food',
    is_bought INTEGER DEFAULT 0,
    bought_price REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS weekly_meal_plans (
    user_id INTEGER PRIMARY KEY,
    plan_json TEXT NOT NULL,
    week_start_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS insights_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    finding_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    suggested_action TEXT,
    detected_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ai_advice (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    week_start TEXT NOT NULL,
    advice_json TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    applied_at TEXT,
    effect_checked_at TEXT,
    effect_result TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS daily_aggregates_archive (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    archive_date TEXT NOT NULL,
    total_calories INTEGER NOT NULL,
    total_protein REAL NOT NULL,
    total_fat REAL NOT NULL,
    total_carbs REAL NOT NULL,
    total_expense REAL NOT NULL,
    total_impulse_expense REAL NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, archive_date),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    response_json TEXT NOT NULL,
    expires_at INTEGER NOT NULL
);

-- Indexes for maximum performance and user-filtered isolation
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_food_entries_user_date ON food_entries(user_id, entry_date);
CREATE INDEX IF NOT EXISTS idx_food_entries_link_id ON food_entries(link_id);
CREATE INDEX IF NOT EXISTS idx_expenses_user_date ON expenses(user_id, expense_date);
CREATE INDEX IF NOT EXISTS idx_expenses_link_id ON expenses(link_id);
CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id);
CREATE INDEX IF NOT EXISTS idx_budgets_user ON budgets(user_id);
CREATE INDEX IF NOT EXISTS idx_schedules_next_run ON schedules(is_active, next_run_at);
CREATE INDEX IF NOT EXISTS idx_schedules_user ON schedules(user_id);
CREATE INDEX IF NOT EXISTS idx_gemini_usage_date ON gemini_usage(call_date);
CREATE INDEX IF NOT EXISTS idx_custom_foods_user ON custom_foods(user_id);
CREATE INDEX IF NOT EXISTS idx_pantry_items_user ON pantry_items(user_id);
CREATE INDEX IF NOT EXISTS idx_water_logs_user_date ON water_logs(user_id, log_date);
CREATE INDEX IF NOT EXISTS idx_weight_logs_user_date ON weight_logs(user_id, log_date);
CREATE INDEX IF NOT EXISTS idx_tasks_user_completed ON tasks(user_id, is_completed);
CREATE INDEX IF NOT EXISTS idx_notes_user_pinned ON notes(user_id, is_pinned);
CREATE INDEX IF NOT EXISTS idx_workout_logs_user_date ON workout_logs(user_id, workout_date);
CREATE INDEX IF NOT EXISTS idx_workout_logs_exercise ON workout_logs(user_id, exercise_name);
CREATE INDEX IF NOT EXISTS idx_idempotency_expires ON idempotency_keys(expires_at);
"""


class DatabaseManager:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON;")
        await conn.execute("PRAGMA journal_mode = WAL;")
        await conn.execute("PRAGMA synchronous = NORMAL;")
        await conn.execute("PRAGMA cache_size = -64000;")
        try:
            yield conn
        finally:
            await conn.close()

    async def init_db(self) -> None:
        """Initialize SQLite tables, run backward-compatible migrations, and indexes."""
        logger.info(f"Initializing database schema at {self.db_path}")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with self.get_connection() as conn:
            await conn.executescript(CREATE_TABLES_SQL)

            # Safe column migrations for existing databases
            migrations = [
                ("expenses", "entry_type", "TEXT DEFAULT 'expense'"),
                ("expenses", "ai_analysis", "TEXT"),
                ("expenses", "is_impulsive", "INTEGER DEFAULT 0"),
                ("expenses", "is_impulse", "INTEGER DEFAULT 0"),
                ("expenses", "impulse_reason", "TEXT"),
                ("expenses", "link_id", "TEXT"),
                ("expenses", "source", "TEXT DEFAULT 'manual'"),
                ("food_entries", "link_id", "TEXT"),
                ("budgets", "impulse_monthly_limit", "REAL DEFAULT 0.0"),
                ("calorie_goals", "training_surplus_pct", "INTEGER DEFAULT 10"),
                ("tasks", "postponed_count", "INTEGER DEFAULT 0"),
                ("check_ins", "satiety", "INTEGER DEFAULT 3"),
            ]
            for table, col, col_type in migrations:
                try:
                    await conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type};")
                except Exception:
                    # Column already exists or table freshly created
                    pass

            await conn.commit()
        logger.info("Database schema initialized successfully.")

    async def optimize_db(self) -> None:
        """Runs SQLite PRAGMA optimize for query planner tuning."""
        async with self.get_connection() as conn:
            await conn.execute("PRAGMA optimize;")
            await conn.commit()

    async def vacuum_db(self) -> None:
        """Runs VACUUM to reclaim free space."""
        async with self.get_connection() as conn:
            await conn.execute("VACUUM;")

    async def get_storage_stats(self) -> Dict[str, Any]:
        """Calculates database file size and row counts for each table."""
        file_size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
        tables_stats: Dict[str, int] = {}
        async with self.get_connection() as conn:
            cur = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
            )
            rows = await cur.fetchall()
            for r in rows:
                tname = r["name"]
                try:
                    count_cur = await conn.execute(f"SELECT COUNT(*) as cnt FROM {tname};")
                    c_row = await count_cur.fetchone()
                    tables_stats[tname] = c_row["cnt"] if c_row else 0
                except Exception:
                    tables_stats[tname] = 0

        return {
            "db_size_bytes": file_size_bytes,
            "db_size_mb": round(file_size_bytes / (1024 * 1024), 2),
            "tables": tables_stats,
        }
