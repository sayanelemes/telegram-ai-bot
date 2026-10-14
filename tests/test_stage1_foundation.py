import pytest
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from app.config.settings import settings
from app.database.repositories.gemini_usage_repository import GeminiUsageRepository
from app.services.gemini import GeminiService, GeminiServiceError
from scripts.backup_db import backup_database, _prune_backups


@pytest.mark.asyncio
async def test_database_wal_and_stats(temp_db_manager):
    # Check WAL mode
    async with temp_db_manager.get_connection() as conn:
        cur = await conn.execute("PRAGMA journal_mode;")
        row = await cur.fetchone()
        assert row[0].lower() == "wal"

    # Check storage stats
    stats = await temp_db_manager.get_storage_stats()
    assert "db_size_bytes" in stats
    assert "tables" in stats
    assert "users" in stats["tables"]
    assert "schedules" in stats["tables"]
    assert "gemini_usage" in stats["tables"]


@pytest.mark.asyncio
async def test_gemini_usage_limits(temp_db_manager, user_repo):
    repo = GeminiUsageRepository(temp_db_manager)
    service = GeminiService(api_key="mock_key", usage_repo=repo)

    tz = ZoneInfo(settings.DEFAULT_TIMEZONE)
    today = datetime.datetime.now(tz).strftime("%Y-%m-%d")

    # Create real user first so foreign key succeeds
    user = await user_repo.get_or_create_user(telegram_id=9999)
    user_id = user.id

    # Increment up to user limit
    for _ in range(settings.MAX_USER_GEMINI_CALLS_PER_DAY):
        await repo.increment_usage(user_id, today)

    # Next call should hit rate limit
    with pytest.raises(GeminiServiceError) as exc_info:
        await service._check_rate_limit(user_id)
    assert "суточного лимита" in str(exc_info.value)


def test_backup_and_pruning(tmp_path):
    # Create fake sqlite db
    db_file = tmp_path / "test.db"
    import sqlite3
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE foo (id INT);")
        conn.execute("INSERT INTO foo VALUES (1);")
        conn.commit()

    backup_dir = tmp_path / "backups"
    created = backup_database(db_path=db_file, backup_dir=backup_dir, max_daily=3, max_weekly=2)
    assert created.exists()
    assert created.suffix == ".gz"

    # Test pruning
    daily_dir = backup_dir / "daily"
    # Create 5 fake backup files
    for i in range(5):
        f = daily_dir / f"test_{i}.db.gz"
        f.write_text("data")
    _prune_backups(daily_dir, max_keep=3)
    remaining = list(daily_dir.glob("*.db.gz"))
    assert len(remaining) <= 3
