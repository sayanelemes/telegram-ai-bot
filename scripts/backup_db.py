import os
import sys
import gzip
import shutil
import sqlite3
import datetime
from pathlib import Path
from typing import Optional

# Ensure project root is in path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.config.settings import settings


def backup_database(
    db_path: Optional[Path] = None,
    backup_dir: Optional[Path] = None,
    max_daily: int = 7,
    max_weekly: int = 4
) -> Path:
    """
    Creates an online atomic SQLite backup, compresses it using gzip,
    and applies a 7-daily / 4-weekly retention policy.
    """
    if db_path is None:
        db_path = settings.resolved_db_path

    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found at {db_path}")

    if backup_dir is None:
        backup_dir = db_path.parent / "backups"

    daily_dir = backup_dir / "daily"
    weekly_dir = backup_dir / "weekly"
    daily_dir.mkdir(parents=True, exist_ok=True)
    weekly_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.datetime.now(datetime.timezone.utc)
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")
    temp_backup_file = backup_dir / f"backup_temp_{timestamp_str}.db"

    # 1. Perform atomic SQLite online backup
    source_conn = sqlite3.connect(str(db_path))
    dest_conn = sqlite3.connect(str(temp_backup_file))
    try:
        source_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        source_conn.close()

    # 2. Compress with gzip into daily backup
    daily_backup_file = daily_dir / f"db_backup_{timestamp_str}.db.gz"
    with open(temp_backup_file, "rb") as f_in, gzip.open(daily_backup_file, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)

    # 3. If Sunday (weekday 6), also copy to weekly backup
    if now.weekday() == 6:
        weekly_backup_file = weekly_dir / f"db_backup_weekly_{timestamp_str}.db.gz"
        shutil.copy2(daily_backup_file, weekly_backup_file)

    # Clean up uncompressed temp file
    if temp_backup_file.exists():
        temp_backup_file.unlink()

    # 4. Retention policy enforcement
    _prune_backups(daily_dir, max_keep=max_daily)
    _prune_backups(weekly_dir, max_keep=max_weekly)

    return daily_backup_file


def _prune_backups(directory: Path, max_keep: int) -> None:
    """Removes older backups exceeding max_keep."""
    backups = sorted(
        directory.glob("*.db.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    for old_file in backups[max_keep:]:
        try:
            old_file.unlink()
        except OSError:
            pass


async def send_backup_to_chat(backup_path: Path, bot, chat_id: int) -> bool:
    """Optional utility to send daily backup to Telegram admin/chat."""
    try:
        from aiogram.types import FSInputFile
        file = FSInputFile(str(backup_path), filename=backup_path.name)
        await bot.send_document(
            chat_id=chat_id,
            document=file,
            caption=f"📦 Резервная копия базы данных ({backup_path.name})"
        )
        return True
    except Exception as e:
        print(f"Failed to send backup to chat: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    try:
        created = backup_database()
        print(f"Backup created successfully: {created}")
    except Exception as e:
        print(f"Backup error: {e}", file=sys.stderr)
        sys.exit(1)
