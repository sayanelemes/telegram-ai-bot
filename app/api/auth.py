import hmac
import hashlib
import json
import base64
import time
import random
import urllib.parse
import logging
import sqlite3
from typing import Optional, Dict, Any
from fastapi import Header, HTTPException, status
from app.config.settings import settings
from app.database.models import UserDB
from app.database.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# In-memory store for 6-digit login codes: code -> {"telegram_id": int, "expires_at": float}
_LOGIN_CODES: Dict[str, Dict[str, Any]] = {}


def create_auth_token(telegram_id: int, bot_token: str = settings.BOT_TOKEN, expires_days: int = 365) -> str:
    """
    Creates a tamper-proof cryptographically signed long-lived token for standalone iOS PWA sessions.
    Valid for expires_days (default 365 days).
    """
    issued_at = int(time.time())
    expires_at = issued_at + (expires_days * 86400)
    salt = hex(random.randint(100000, 999999))[2:]
    payload_str = f"{telegram_id}:{issued_at}:{expires_at}:{salt}"
    b64_payload = base64.urlsafe_b64encode(payload_str.encode("utf-8")).decode("utf-8").rstrip("=")

    secret_key = hmac.new(b"StandaloneWebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    sig = hmac.new(secret_key, b64_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{b64_payload}.{sig}"


def validate_auth_token(token: str, bot_token: str = settings.BOT_TOKEN) -> Optional[int]:
    """
    Validates signed standalone auth token and returns telegram_id if valid and not expired.
    """
    if not token or "." not in token:
        return None
    try:
        b64_payload, received_sig = token.split(".", 1)
        secret_key = hmac.new(b"StandaloneWebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
        calculated_sig = hmac.new(secret_key, b64_payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calculated_sig, received_sig):
            return None

        padded_b64 = b64_payload + "=" * ((4 - len(b64_payload) % 4) % 4)
        payload_str = base64.urlsafe_b64decode(padded_b64).decode("utf-8")
        parts = payload_str.split(":")
        if len(parts) < 3:
            return None
        telegram_id = int(parts[0])
        expires_at = int(parts[2])
        if time.time() > expires_at:
            return None
        return telegram_id
    except Exception as e:
        logger.debug(f"Standalone token validation exception: {e}")
        return None


def create_login_code(telegram_id: int, expires_minutes: int = 30) -> str:
    """
    Generates a 6-digit login code valid for expires_minutes.
    Stored in SQLite for cross-process access and persistence.
    """
    code = f"{random.randint(100000, 999999)}"
    now = time.time()
    expires_at = now + (expires_minutes * 60)
    db_path = str(settings.DATABASE_PATH)
    try:
        with sqlite3.connect(db_path, timeout=10.0) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS login_codes (code TEXT PRIMARY KEY, telegram_id INTEGER NOT NULL, expires_at REAL NOT NULL)")
            conn.execute("DELETE FROM login_codes WHERE expires_at < ?", (now,))
            conn.execute("INSERT OR REPLACE INTO login_codes (code, telegram_id, expires_at) VALUES (?, ?, ?)", (code, telegram_id, expires_at))
            conn.commit()
    except Exception as e:
        logger.error(f"Error saving login code to SQLite: {e}")
        _LOGIN_CODES[code] = {"telegram_id": telegram_id, "expires_at": expires_at}
    return code


def verify_login_code(code: str) -> Optional[int]:
    """
    Verifies a 6-digit login code and returns telegram_id on success. Single-use.
    """
    clean_code = code.replace(" ", "").replace("-", "").strip()
    now = time.time()
    db_path = str(settings.DATABASE_PATH)
    try:
        with sqlite3.connect(db_path, timeout=10.0) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS login_codes (code TEXT PRIMARY KEY, telegram_id INTEGER NOT NULL, expires_at REAL NOT NULL)")
            cur = conn.cursor()
            cur.execute("SELECT telegram_id, expires_at FROM login_codes WHERE code = ?", (clean_code,))
            row = cur.fetchone()
            if row:
                tg_id, expires_at = row[0], row[1]
                conn.execute("DELETE FROM login_codes WHERE code = ?", (clean_code,))
                conn.commit()
                if now <= expires_at:
                    return tg_id
    except Exception as e:
        logger.error(f"Error querying login code from SQLite: {e}")

    # Fallback to in-memory
    entry = _LOGIN_CODES.get(clean_code)
    if entry:
        _LOGIN_CODES.pop(clean_code, None)
        if now <= entry["expires_at"]:
            return entry["telegram_id"]
    return None


def validate_telegram_init_data(init_data: str, bot_token: str) -> Optional[Dict[str, Any]]:
    """
    Validates Telegram WebApp initData string using HMAC-SHA256 according to Telegram specifications.
    Returns parsed user dict if valid, None otherwise.
    """
    if not init_data or not bot_token:
        return None

    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        if "hash" not in parsed:
            return None

        received_hash = parsed.pop("hash")
        # All remaining keys sorted alphabetically, joined by newline
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

        # Secret key: HMAC-SHA-256 of bot_token using "WebAppData" as key
        secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
        # Calculated hash
        calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            return None

        user_json = parsed.get("user")
        if not user_json:
            return None

        user_data = json.loads(user_json)
        return user_data
    except Exception as e:
        logger.warning(f"Failed to validate telegram initData: {e}")
        return None


async def get_current_user_from_init_data(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data"),
    x_auth_token: Optional[str] = Header(None, alias="X-Auth-Token"),
    x_dev_user_id: Optional[str] = Header(None, alias="X-Dev-User-Id"),
    user_repo: UserRepository = None,  # Will be injected
) -> UserDB:
    """
    FastAPI dependency to extract and authenticate user.
    Supports:
    1. Standalone auth token (from localStorage on iOS Home Screen or X-Auth-Token / Bearer).
    2. Telegram WebApp initData (from inside Telegram).
    3. Dev user fallback for tests.
    """
    token_candidate = None
    if x_auth_token:
        token_candidate = x_auth_token
    elif authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token_candidate = parts[1]

    # 1. First, attempt to validate as standalone PWA token
    if token_candidate:
        tg_id = validate_auth_token(token_candidate, settings.BOT_TOKEN)
        if tg_id:
            user = await user_repo.get_by_telegram_id(tg_id)
            if not user:
                user = await user_repo.get_or_create_user(
                    telegram_id=tg_id,
                    username=None,
                    first_name="Пользователь",
                    timezone=settings.DEFAULT_TIMEZONE,
                )
            return user

    # 2. Check for Telegram initData
    init_data = x_telegram_init_data
    if not init_data and authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() in ("bearer", "tma"):
            init_data = parts[1]
        else:
            init_data = authorization

    user_info = None
    if init_data:
        user_info = validate_telegram_init_data(init_data, settings.BOT_TOKEN)

    # 3. Allow X-Dev-User-Id strictly for testing/dev if bot token is mock/test or WEB_APP_URL is localhost
    is_dev_env = (
        settings.BOT_TOKEN.startswith("mock")
        or "test" in settings.BOT_TOKEN.lower()
        or "localhost" in settings.WEB_APP_URL.lower()
        or "127.0.0.1" in settings.WEB_APP_URL.lower()
    )
    if not user_info and x_dev_user_id and is_dev_env:
        try:
            user_info = {"id": int(x_dev_user_id), "first_name": "Dev User", "username": "dev_user"}
        except ValueError:
            pass

    if not user_info or "id" not in user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительные или отсутствующие данные авторизации Telegram (initData).",
            headers={"WWW-Authenticate": "Bearer"},
        )

    telegram_id = int(user_info["id"])
    first_name = user_info.get("first_name", "Пользователь")
    username = user_info.get("username")

    user = await user_repo.get_or_create_user(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        timezone=settings.DEFAULT_TIMEZONE,
    )
    return user
