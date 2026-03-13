import os
from pathlib import Path
from dotenv import dotenv_values
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get app directory (where config.py is located)
APP_DIR = Path(__file__).parent
PROJECT_DIR = APP_DIR.parent


def _get_env_files() -> tuple[str, ...]:
    env_files: list[str] = []

    app_env = APP_DIR / ".env"
    project_env = PROJECT_DIR / ".env"

    if app_env.exists():
        env_files.append(str(app_env))

    if project_env.exists() and project_env != app_env:
        env_files.append(str(project_env))

    return tuple(env_files)


def _bootstrap_prefixed_environment() -> None:
    for key, value in list(os.environ.items()):
        if key.startswith("_APP_"):
            os.environ.setdefault(key[1:], value)

    for env_file in _get_env_files():
        for key, value in dotenv_values(env_file).items():
            if key and value is not None and key.startswith("_APP_"):
                os.environ.setdefault(key[1:], value)


_bootstrap_prefixed_environment()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore"
    )

    # API Paths
    APP_ROOT_PATH: str = ""
    APP_API_PREFIX: str = "/api/v1"
    APP_CORS_ALLOW_ORIGINS: str = ""
    APP_CORS_ALLOW_CREDENTIALS: bool = False
    APP_CORS_ALLOW_METHODS: str = "GET,POST,DELETE,OPTIONS"
    APP_CORS_ALLOW_HEADERS: str = "*"

    # Cache
    APP_CACHE_DIR: Path = Path("./cache")
    APP_MAX_CACHE_SIZE_MB: int = 1000
    APP_CACHE_TTL_DAYS: int = 30
    APP_JOBS_DIR: Path = Path("./cache/jobs")
    APP_WORK_DIR: Path = Path("./cache/work")

    # Functionality
    APP_USE_CACHE_DEFAULT: bool = True
    APP_TRANSCRIPT_FROM_AUDIO: bool = False
    APP_MCP_HIDE_CLEAR_CACHE: bool = False
    APP_BACKGROUND_JOB_CONCURRENCY: int = 1
    APP_JOB_POLL_TTL_DAYS: int = 7
    APP_JOB_CLEANUP_TEMP_FILES: bool = True

    # Transcription
    APP_TRANSCRIPTION_BACKEND: str = "faster-whisper"
    APP_WHISPER_MODEL: str = "large-v3"
    APP_WHISPER_DEVICE: str = "cpu"
    APP_WHISPER_COMPUTE_TYPE: str = "int8"
    APP_YTDLP_SOCKET_TIMEOUT_SECONDS: int = 120
    APP_FFMPEG_AUDIO_RATE: int = 16000
    APP_FFMPEG_AUDIO_CHANNELS: int = 1
    APP_TRANSCRIPTION_PROVIDER_TIMEOUT_SECONDS: int = 1800
    APP_TRANSCRIPTION_PROVIDER_POLL_SECONDS: int = 3
    APP_API_KEY: str = ""
    APP_BASE_URL: str = ""
    APP_MODEL: str = ""
    APP_LANGUAGE_DETECTION: bool = True
    APP_GEMINI_TRANSCRIPTION_PROMPT: str = (
        "Transcribe this audio verbatim. Return JSON with keys 'transcript' and 'language'. "
        "The 'language' value should be a short language code if detectable, otherwise 'unknown'."
    )

    # API Key Authentication
    APP_X_API_KEY: str = ""
    APP_X_API_KEY_HEADER: str = "X-API-Key"

    # System
    APP_LOG_LEVEL: str = "INFO"
    APP_PORT: int = 8000

    @property
    def api_key_value(self) -> str:
        return (self.APP_X_API_KEY or self.APP_API_KEY or "").strip()

    @property
    def cors_allow_origins(self) -> list[str]:
        return [origin.strip() for origin in self.APP_CORS_ALLOW_ORIGINS.split(",") if origin.strip()]

    @property
    def cors_allow_methods(self) -> list[str]:
        return [method.strip() for method in self.APP_CORS_ALLOW_METHODS.split(",") if method.strip()]

    @property
    def cors_allow_headers(self) -> list[str]:
        return [header.strip() for header in self.APP_CORS_ALLOW_HEADERS.split(",") if header.strip()]


settings = Settings()
