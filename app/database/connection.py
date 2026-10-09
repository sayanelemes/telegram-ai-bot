import logging
from pathlib import Path
from typing import AsyncGenerator
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
    description TEXT,
    raw_text TEXT,
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
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_food_entries_user_date ON food_entries(user_id, entry_date);
CREATE INDEX IF NOT EXISTS idx_expenses_user_date ON expenses(user_id, expense_date);
CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id);
CREATE INDEX IF NOT EXISTS idx_budgets_user ON budgets(user_id);
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
        try:
            yield conn
        finally:
            await conn.close()

    async def init_db(self) -> None:
        """Initialize SQLite tables, run migrations, and indexes."""
        logger.info(f"Initializing database schema at {self.db_path}")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with self.get_connection() as conn:
            await conn.executescript(CREATE_TABLES_SQL)

            # Safe column migrations for existing databases
            migrations = [
                ("expenses", "entry_type", "TEXT DEFAULT 'expense'"),
                ("expenses", "ai_analysis", "TEXT"),
                ("expenses", "is_impulsive", "INTEGER DEFAULT 0"),
            ]
            for table, col, col_type in migrations:
                try:
                    await conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type};")
                except Exception:
                    # Column already exists
                    pass

            await conn.commit()
        logger.info("Database schema initialized successfully.")
