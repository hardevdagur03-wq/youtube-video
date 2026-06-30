"""Custom exception classes package initialization."""
from .youtube_errors import YouTubeURLError, InvalidVideoIDError, UnsupportedURLError
from .analysis_errors import (
    AnalysisError,
    LLMProviderError,
    LLMAuthenticationError,
    LLMRateLimitError,
    LLMContextLengthError,
    LLMTimeoutError,
    PromptInjectionError,
    InvalidTranscriptError,
    AnalysisCacheError,
    AnalysisConfigurationError,
)

__all__ = [
    "YouTubeURLError",
    "InvalidVideoIDError",
    "UnsupportedURLError",
    "AnalysisError",
    "LLMProviderError",
    "LLMAuthenticationError",
    "LLMRateLimitError",
    "LLMContextLengthError",
    "LLMTimeoutError",
    "PromptInjectionError",
    "InvalidTranscriptError",
    "AnalysisCacheError",
    "AnalysisConfigurationError",
]
