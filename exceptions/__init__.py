"""Custom exception classes package initialization."""
from .youtube_errors import YouTubeURLError, InvalidVideoIDError, UnsupportedURLError

__all__ = [
    "YouTubeURLError",
    "InvalidVideoIDError",
    "UnsupportedURLError",
]
