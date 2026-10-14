from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class Settings(BaseSettings):
    BOT_TOKEN: str = Field(default="", description="Telegram Bot API Token")
    GEMINI_API_KEY: str = Field(default="", description="Google Gemini API Key")
    DATABASE_PATH: str = Field(default="data/bot.db", description="Path to SQLite database file")
    DEFAULT_TIMEZONE: str = Field(default="Asia/Almaty", description="Default user timezone")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    MAX_IMAGE_SIZE_MB: int = Field(default=10, description="Max allowed image upload size in MB")
    RATE_LIMIT_PER_MINUTE: int = Field(default=20, description="Rate limit per user per minute")
    GEMINI_MODEL: str = Field(default="gemini-3.5-flash", description="Gemini model name")
    MAX_USER_GEMINI_CALLS_PER_DAY: int = Field(default=50, description="Max Gemini calls per user per day")
    MAX_GLOBAL_GEMINI_CALLS_PER_DAY: int = Field(default=500, description="Max Gemini calls globally per day")
    CURRENCY: str = Field(default="₸", description="Default currency")
    MAX_MEAL_COST: float = Field(default=1500.0, description="Default max cost per meal in recipes")
    WEB_APP_URL: str = Field(default="http://localhost:8000", description="URL where Telegram WebApp is served")
    API_HOST: str = Field(default="0.0.0.0", description="Host to bind FastAPI server")
    STATIC_DIR: str = Field(default="webapp/dist", description="Path to static webapp assets")
    HTTPS_PROXY: Optional[str] = Field(default=None, description="HTTP/HTTPS proxy for outbound requests")
    GEMINI_BASE_URL: Optional[str] = Field(default=None, description="Custom base URL for Gemini API")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("DEFAULT_TIMEZONE")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
            return v
        except ZoneInfoNotFoundError:
            return "Asia/Almaty"

    @property
    def max_image_bytes(self) -> int:
        return self.MAX_IMAGE_SIZE_MB * 1024 * 1024

    @property
    def resolved_db_path(self) -> Path:
        path = Path(self.DATABASE_PATH)
        if not path.is_absolute():
            # Project root is two levels up from app/config
            project_root = Path(__file__).resolve().parent.parent.parent
            path = project_root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
