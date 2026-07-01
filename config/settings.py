"""Application settings.

Loads from .env file and validates all required configuration.
Provides a singleton ``settings`` instance for use throughout the application.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(Exception):
    """Exception raised when there is an error in application configuration."""
    pass


# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env before anything else
_ENV_FILE = BASE_DIR / ".env"
if _ENV_FILE.exists():
    load_dotenv(dotenv_path=_ENV_FILE, override=True)


_PLACEHOLDER_VALUES = {"", "your_youtube_api_key_here", "your_api_key_here", "your-api-key"}


def validate_youtube_api_key(v: str) -> str:
    """Validate that the YouTube API key is not empty or a placeholder.

    Raises ConfigurationError if the key is missing or a placeholder.
    """
    stripped = v.strip()
    if not stripped or stripped.lower() in _PLACEHOLDER_VALUES:
        raise ConfigurationError(
            f"YouTube API key is missing or has a placeholder value.\n"
            f"Please add a valid YOUTUBE_API_KEY to your .env file at: {BASE_DIR / '.env'}"
        )
    return stripped


def is_youtube_api_key_valid() -> tuple[bool, str]:
    """Check if the YouTube API key is configured without raising."""
    raw = os.getenv("YOUTUBE_API_KEY", "")
    try:
        validate_youtube_api_key(raw)
        return True, ""
    except ConfigurationError as e:
        return False, str(e)


class Settings:
    """Centralized application settings.

    Loads values from environment variables (sourced from .env via python-dotenv).
    Does NOT raise on missing API key at construction — validation happens at
    point of use via ``validate_youtube_api_key()``.
    """

    # Required (validated at point of use)
    youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "")

    # Optional API keys for AI features
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")

    # Application settings
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # Paths
    base_dir: Path = BASE_DIR
    logs_dir: Path = BASE_DIR / "logs"
    output_dir: Path = BASE_DIR / "output"

    # HTTP client settings
    http_connect_timeout: int = 15
    http_read_timeout: int = 30
    http_max_retries: int = 3
    http_backoff_factor: float = 1.0

    # YouTube API settings
    youtube_max_results: int = 50
    youtube_batch_size: int = 50
    youtube_quota_warning: int = 8000

    def __init__(self) -> None:
        """Create directories on initialization."""
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)


# Singleton settings instance
try:
    settings = Settings()
except Exception:
    import logging
    logging.warning("Failed to initialize Settings directories", exc_info=True)

    class _FallbackSettings:
        youtube_api_key = os.getenv("YOUTUBE_API_KEY", "")
        log_level = os.getenv("LOG_LEVEL", "INFO")
        base_dir = BASE_DIR
        logs_dir = BASE_DIR / "logs"
        output_dir = BASE_DIR / "output"
        http_connect_timeout = 15
        http_read_timeout = 30
        http_max_retries = 3
        http_backoff_factor = 1.0
        youtube_max_results = 50
        youtube_batch_size = 50
        youtube_quota_warning = 8000
        openai_api_key = os.getenv("OPENAI_API_KEY", "")
        gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    settings = _FallbackSettings()  # type: ignore[assignment]
