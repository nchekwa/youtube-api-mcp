from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get app directory (where config.py is located)
APP_DIR = Path(__file__).parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(APP_DIR / ".env"),
        env_file_encoding="utf-8",
        env_prefix="_APP_",
        case_sensitive=False,
        extra="ignore"
    )

    # API Paths
    APP_ROOT_PATH: str = ""
    APP_API_PREFIX: str = "/api/v1"

    # Cache
    APP_CACHE_DIR: Path = Path("./cache")
    APP_MAX_CACHE_SIZE_MB: int = 1000
    APP_CACHE_TTL_DAYS: int = 30

    # Functionality
    APP_USE_CACHE_DEFAULT: bool = True

    # API Key Authentication
    APP_X_API_KEY: str = ""
    APP_X_API_KEY_HEADER: str = "X-API-Key"

    # System
    APP_LOG_LEVEL: str = "INFO"
    APP_PORT: int = 8000


settings = Settings()
