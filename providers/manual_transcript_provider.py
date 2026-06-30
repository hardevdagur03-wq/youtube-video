"""Stage 1: Official YouTube human-created transcript provider."""

import logging

from models.transcript import (
    TranscriptResult,
    TranscriptSource,
    TranscriptProviderName,
    PipelineStep,
)
from interfaces.transcript_provider import TranscriptProvider
from clients.youtube_transcript_client import (
    YouTubeTranscriptClient,
    NoTranscriptFoundError,
    TranscriptsDisabledError,
    VideoUnavailableError,
    TooManyRequestsError,
)
from utils.text_cleaner import TextCleaner
from utils.language_detector import LanguageDetector
from utils.read_time import estimate_read_time

logger = logging.getLogger(__name__)


class ManualTranscriptProvider(TranscriptProvider):
    """Stage 1 provider: retrieves official manually created YouTube transcripts.

    This is the highest-priority source. Manually created captions
    have the best accuracy, punctuation, and formatting.
    """

    def __init__(
        self,
        client: YouTubeTranscriptClient | None = None,
        text_cleaner: TextCleaner | None = None,
        language_detector: LanguageDetector | None = None,
    ) -> None:
        self._client = client or YouTubeTranscriptClient()
        self._text_cleaner = text_cleaner or TextCleaner()
        self._language_detector = language_detector or LanguageDetector()

    def name(self) -> str:
        return "Manual Transcript"

    def get_transcript(
        self, video_id: str, language: str | None = None
    ) -> TranscriptResult:
        """Fetch official manually created transcript.

        Args:
            video_id: 11-character YouTube video ID.
            language: Optional language code.

        Returns:
            ``TranscriptResult`` populated with manual transcript data.

        Raises:
            NoTranscriptFoundError: No manual transcript available.
            TranscriptsDisabledError: Transcripts disabled.
            VideoUnavailableError: Video unavailable.
        """
        result = TranscriptResult(
            video_id=video_id,
            source=TranscriptSource.MANUAL,
            provider=TranscriptProviderName.YOUTUBE_MANUAL,
        )

        try:
            languages = [language] if language else None
            raw_segments = self._client.fetch_transcript(
                video_id, languages=languages, prefer_manual=True
            )
        except (NoTranscriptFoundError, TranscriptsDisabledError, VideoUnavailableError,
                TooManyRequestsError):
            raise
        except Exception as exc:
            logger.warning("Manual transcript fetch failed for %s: %s", video_id, exc)
            raise NoTranscriptFoundError(f"Manual transcript unavailable: {exc}")

        if not raw_segments:
            raise NoTranscriptFoundError(f"No manual transcript segments for {video_id}")

        segments = self._client.parse_segments(raw_segments)
        segments = self._text_cleaner.clean_segments(segments)

        plain_text = " ".join(seg.text for seg in segments)
        paragraph_text = self._text_cleaner.build_paragraphs(segments)
        word_count = len(plain_text.split())
        char_count = len(plain_text)
        duration = segments[-1].end if segments else 0

        detected_lang = self._language_detector.detect(plain_text)

        return TranscriptResult(
            success=True,
            video_id=video_id,
            source=TranscriptSource.MANUAL,
            provider=TranscriptProviderName.YOUTUBE_MANUAL,
            language=detected_lang.language if detected_lang else (language or "en"),
            language_confidence=detected_lang.confidence if detected_lang else None,
            segments=segments,
            plain_text=plain_text,
            paragraph_text=paragraph_text,
            word_count=word_count,
            character_count=char_count,
            estimated_read_time=estimate_read_time(word_count),
            duration_seconds=duration,
            error=None,
        )
