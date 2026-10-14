import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from pathlib import Path

from app.database.connection import DatabaseManager

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def get_storage_stats(self) -> Dict[str, Any]:
        """
        Collect SQLite database metrics:
        - DB file size in bytes and formatted string
        - Free pages and page count
        - Exact row counts for all tables
        - Count of archivable records (> 12 months old)
        """
        async with self.db.get_connection() as conn:
            cur_p = await conn.execute("PRAGMA page_count;")
            r_page_count = await cur_p.fetchone()
            page_count = int(r_page_count[0]) if r_page_count else 0

            cur_s = await conn.execute("PRAGMA page_size;")
            r_page_size = await cur_s.fetchone()
            page_size = int(r_page_size[0]) if r_page_size else 4096

            cur_f = await conn.execute("PRAGMA freelist_count;")
            r_freelist = await cur_f.fetchone()
            freelist_count = int(r_freelist[0]) if r_freelist else 0

            # Measure file size
            try:
                db_path = Path(self.db.db_path)
                size_bytes = os.path.getsize(db_path) if db_path.exists() else (page_count * page_size)
            except Exception:
                size_bytes = page_count * page_size

            # Table row counts
            tables_to_count = [
                "users",
                "food_entries",
                "food_items",
                "expenses",
                "expense_items",
                "water_logs",
                "weight_logs",
                "tasks",
                "notes",
                "habits",
                "habit_logs",
                "check_ins",
                "workout_logs",
                "savings_goals",
                "subscriptions",
                "debts",
                "schedules",
                "insights_findings",
                "ai_advice",
                "daily_aggregates_archive",
                "last_recipes",
                "pantry_items",
            ]

            table_counts: Dict[str, int] = {}
            for t in tables_to_count:
                try:
                    cur_t = await conn.execute(f"SELECT COUNT(*) as cnt FROM {t};")
                    r_t = await cur_t.fetchone()
                    table_counts[t] = int(r_t["cnt"]) if r_t else 0
                except Exception:
                    table_counts[t] = 0

            # Archivable records (> 12 months)
            cutoff_date = (datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d")
            cur_af = await conn.execute("SELECT COUNT(*) as cnt FROM food_entries WHERE entry_date < ?;", (cutoff_date,))
            r_af = await cur_af.fetchone()
            archivable_food = int(r_af["cnt"]) if r_af else 0

            cur_ae = await conn.execute("SELECT COUNT(*) as cnt FROM expenses WHERE expense_date < ?;", (cutoff_date,))
            r_ae = await cur_ae.fetchone()
            archivable_exp = int(r_ae["cnt"]) if r_ae else 0

            reclaimable_kb = (freelist_count * page_size) // 1024

            return {
                "db_size_bytes": size_bytes,
                "db_size_mb": round(size_bytes / (1024 * 1024), 2),
                "db_size_formatted": f"{size_bytes / (1024 * 1024):.2f} MB" if size_bytes >= 1024 * 1024 else f"{size_bytes / 1024:.1f} KB",
                "page_count": page_count,
                "page_size": page_size,
                "freelist_count": freelist_count,
                "reclaimable_freelist_kb": reclaimable_kb,
                "tables": table_counts,
                "archivable": {
                    "cutoff_date": cutoff_date,
                    "food_entries": archivable_food,
                    "expenses": archivable_exp,
                    "total_archivable": archivable_food + archivable_exp,
                },
            }

    async def archive_and_vacuum(self, cutoff_days: int = 365) -> Dict[str, Any]:
        """
        Archive detailed food entries and expenses older than cutoff_days (default 12 months)
        into daily_aggregates_archive, clean up TTL caches, and run PRAGMA optimize + VACUUM.
        """
        stats_before = await self.get_storage_stats()
        cutoff_date = (datetime.utcnow() - timedelta(days=cutoff_days)).strftime("%Y-%m-%d")

        async with self.db.get_connection() as conn:
            # 1. Archive food entries into daily_aggregates_archive
            await conn.execute(
                """
                INSERT INTO daily_aggregates_archive (
                    user_id, archive_date, total_calories, total_protein, total_fat, total_carbs, total_expense, total_impulse_expense, created_at
                )
                SELECT
                    fe.user_id,
                    fe.entry_date as archive_date,
                    COALESCE(SUM(fe.total_calories), 0) as total_calories,
                    COALESCE(SUM(fe.total_protein), 0.0) as total_protein,
                    COALESCE(SUM(fe.total_fat), 0.0) as total_fat,
                    COALESCE(SUM(fe.total_carbs), 0.0) as total_carbs,
                    0.0 as total_expense,
                    0.0 as total_impulse_expense,
                    datetime('now') as created_at
                FROM food_entries fe
                WHERE fe.entry_date < ?
                GROUP BY fe.user_id, fe.entry_date
                ON CONFLICT(user_id, archive_date) DO UPDATE SET
                    total_calories = excluded.total_calories,
                    total_protein = excluded.total_protein,
                    total_fat = excluded.total_fat,
                    total_carbs = excluded.total_carbs;
                """,
                (cutoff_date,)
            )

            # 2. Archive expenses into daily_aggregates_archive
            await conn.execute(
                """
                INSERT INTO daily_aggregates_archive (
                    user_id, archive_date, total_calories, total_protein, total_fat, total_carbs, total_expense, total_impulse_expense, created_at
                )
                SELECT
                    e.user_id,
                    e.expense_date as archive_date,
                    0 as total_calories,
                    0.0 as total_protein,
                    0.0 as total_fat,
                    0.0 as total_carbs,
                    COALESCE(SUM(e.amount), 0.0) as total_expense,
                    COALESCE(SUM(CASE WHEN e.is_impulse = 1 OR e.is_impulsive = 1 THEN e.amount ELSE 0.0 END), 0.0) as total_impulse_expense,
                    datetime('now') as created_at
                FROM expenses e
                WHERE e.expense_date < ?
                GROUP BY e.user_id, e.expense_date
                ON CONFLICT(user_id, archive_date) DO UPDATE SET
                    total_expense = excluded.total_expense,
                    total_impulse_expense = excluded.total_impulse_expense;
                """,
                (cutoff_date,)
            )

            # 3. Delete old detailed records
            await conn.execute(
                "DELETE FROM food_items WHERE food_entry_id IN (SELECT id FROM food_entries WHERE entry_date < ?);",
                (cutoff_date,)
            )
            await conn.execute("DELETE FROM food_entries WHERE entry_date < ?;", (cutoff_date,))

            await conn.execute(
                "DELETE FROM expense_items WHERE expense_id IN (SELECT id FROM expenses WHERE expense_date < ?);",
                (cutoff_date,)
            )
            await conn.execute("DELETE FROM expenses WHERE expense_date < ?;", (cutoff_date,))

            # 4. Clean up TTL caches and expired temporary records
            now_ts = int(datetime.utcnow().timestamp())
            await conn.execute("DELETE FROM idempotency_keys WHERE expires_at < ?;", (now_ts,))
            await conn.execute("DELETE FROM last_recipes WHERE created_at < ?;", (now_ts - 7 * 86400,))
            await conn.execute("DELETE FROM insights_findings WHERE detected_at < date('now', '-90 days');")

            # 5. Commit deletions and summaries
            await conn.commit()

            # 6. Optimize PRAGMA & VACUUM
            await conn.execute("PRAGMA optimize;")
            await conn.execute("VACUUM;")

        stats_after = await self.get_storage_stats()
        reclaimed_bytes = max(0, stats_before["db_size_bytes"] - stats_after["db_size_bytes"])

        return {
            "status": "ok",
            "cutoff_date": cutoff_date,
            "archived_food_records": stats_before["archivable"]["food_entries"],
            "archived_expense_records": stats_before["archivable"]["expenses"],
            "initial_db_size_mb": stats_before["db_size_mb"],
            "final_db_size_mb": stats_after["db_size_mb"],
            "reclaimed_bytes": reclaimed_bytes,
            "reclaimed_kb": reclaimed_bytes // 1024,
            "message": f"Архивация завершена! Освобождено {reclaimed_bytes // 1024} КБ.",
        }
