import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(dotenv_path=BASE_DIR / ".env")

class ConfigurationError(Exception):
    """Exception raised when there is an error in application configuration."""
    pass

class Settings:
    """Centralized application settings and configuration management."""

    def __init__(self) -> None:
        self.youtube_api_key: str = self._get_required_env("YOUTUBE_API_KEY")
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
        self.base_dir: Path = BASE_DIR
        self.logs_dir: Path = BASE_DIR / "logs"
        self.output_dir: Path = BASE_DIR / "output"
        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
        
        # Ensure standard directories exist
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_required_env(self, key: str) -> str:
        """Retrieve environment variable or raise ConfigurationError if missing/empty."""
        value = os.getenv(key)
        if not value or value.strip() == "" or value.strip() == "YOUR_YOUTUBE_API_KEY_HERE":
            raise ConfigurationError(
                f"Required environment variable '{key}' is missing or has a placeholder value in your .env file.\n"
                f"Please verify your configuration."
            )
        return value.strip()

# Singleton settings instance
settings = Settings()
