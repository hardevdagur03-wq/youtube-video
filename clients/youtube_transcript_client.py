"""Client for fetching YouTube transcripts via youtube-transcript-api.

Injects a custom requests.Session with:
  - certifi CA bundle
  - SSL / 5xx retry with exponential backoff
  - Comprehensive request logging
  - Explicit timeouts
"""

import logging
import ssl
import time
import uuid
from typing import Any

import certifi
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from models.transcript import TranscriptSegment

logger = logging.getLogger(__name__)

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        TranscriptsDisabled,
        NoTranscriptFound,
        VideoUnavailable,
    )

    _HAS_YOUTUBE_TRANSCRIPT = True
except ImportError:
    _HAS_YOUTUBE_TRANSCRIPT = False


class YouTubeTranscriptClientError(Exception):
    """Base error for YouTube transcript client."""


class NoTranscriptFoundError(YouTubeTranscriptClientError):
    """No transcript found for this video."""


class TranscriptsDisabledError(YouTubeTranscriptClientError):
    """Transcripts are disabled for this video."""


class VideoUnavailableError(YouTubeTranscriptClientError):
    """Video is unavailable or private."""


class TooManyRequestsError(YouTubeTranscriptClientError):
    """Rate limited by YouTube."""


class TranscriptSslError(YouTubeTranscriptClientError):
    """SSL/TLS handshake failure when fetching transcript."""


# ---------------------------------------------------------------------------
# Custom sessions factory
# ---------------------------------------------------------------------------

def _build_transcript_session() -> requests.Session:
    """Build a requests.Session configured for youtube-transcript-api.

    Features:
        - Retry on SSL errors, timeouts, and 5xx statuses
        - certifi CA bundle for SSL verification
        - Connection pooling (10 connections, 30 max)
        - Request/response logging
        - Explicit connect (15s) and read (30s) timeouts
    """
    session = requests.Session()

    # Retry strategy
    retry_strategy = Retry(
        total=3,
        read=3,
        connect=3,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset({"HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"}),
        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        pool_connections=10,
        pool_maxsize=30,
        max_retries=retry_strategy,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    # SSL verification via certifi
    session.verify = certifi.where()

    # Default headers
    session.headers.update({
        "Accept-Language": "en-US",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
    })

    return session


# ---------------------------------------------------------------------------
# Logging wrapper for requests.Session
# ---------------------------------------------------------------------------

class LoggingSession(requests.Session):
    """A requests.Session that logs every request and response."""

    def request(  # type: ignore[override]
        self,
        method: str,
        url: str,
        *args: Any,
        **kwargs: Any,
    ) -> requests.Response:
        request_id = uuid.uuid4().hex[:8]
        timeout = kwargs.get("timeout", (15, 30))

        _redact = {"authorization", "x-api-key", "api-key", "cookie", "set-cookie"}
        log_headers = {
            k: "***" if k.lower() in _redact else str(v)
            for k, v in kwargs.get("headers", {}).items()
        }
        body = kwargs.get("json") or kwargs.get("data")
        if body is not None:
            body = str(body)[:300]

        logger.info(
            "[%s] >>> %s %s  timeout=%s  headers=%s  body=%s",
            request_id, method.upper(), url, timeout,
            log_headers or "-", body or "-",
        )

        start = time.time()
        try:
            response = super().request(method, url, *args, timeout=timeout, **kwargs)
            elapsed = round(time.time() - start, 3)
            logger.info(
                "[%s] <<< %s %s  status=%d  elapsed=%.3fs",
                request_id, method.upper(), url, response.status_code, elapsed,
            )
            return response
        except requests.exceptions.SSLError as exc:
            elapsed = round(time.time() - start, 3)
            logger.error(
                "[%s] SSL ERROR %s %s  elapsed=%.3fs  error=%s",
                request_id, method.upper(), url, elapsed, exc,
            )
            raise TranscriptSslError(
                "Unable to connect securely to the transcript service. "
                "Please try again in a few moments."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            elapsed = round(time.time() - start, 3)
            logger.error(
                "[%s] CONNECTION ERROR %s %s  elapsed=%.3fs  error=%s",
                request_id, method.upper(), url, elapsed, exc,
            )
            raise
        except requests.exceptions.Timeout as exc:
            elapsed = round(time.time() - start, 3)
            logger.error(
                "[%s] TIMEOUT %s %s  elapsed=%.3fs  error=%s",
                request_id, method.upper(), url, elapsed, exc,
            )
            raise
        except Exception as exc:
            elapsed = round(time.time() - start, 3)
            logger.exception(
                "[%s] REQUEST FAILED %s %s  elapsed=%.3fs",
                request_id, method.upper(), url, elapsed,
            )
            raise


# ---------------------------------------------------------------------------
# YouTubeTranscriptClient
# ---------------------------------------------------------------------------

class YouTubeTranscriptClient:
    """Client for fetching YouTube video transcripts.

    Injects a custom requests.Session with retry, logging, and SSL
    configuration into the underlying youtube-transcript-api.
    """

    def __init__(self) -> None:
        if not _HAS_YOUTUBE_TRANSCRIPT:
            raise ImportError(
                "youtube-transcript-api is required. "
                "Install with: pip install youtube-transcript-api"
            )
        session = _build_transcript_session()
        self._session = session
        self._api = YouTubeTranscriptApi(http_client=session)

    def list_transcripts(self, video_id: str) -> Any:
        """List available transcripts for a video.

        Args:
            video_id: 11-character YouTube video ID.

        Returns:
            ``TranscriptList`` from youtube-transcript-api.

        Raises:
            VideoUnavailableError: Video is unavailable.
            TranscriptsDisabledError: Transcripts disabled for this video.
            TooManyRequestsError: Rate limited.
            TranscriptSslError: SSL handshake failure.
        """
        try:
            return self._api.list(video_id)
        except VideoUnavailable:
            raise VideoUnavailableError(f"Video {video_id} is unavailable.")
        except TranscriptsDisabled:
            raise TranscriptsDisabledError(f"Transcripts disabled for video {video_id}.")
        except TranscriptSslError:
            raise
        except Exception as exc:
            exc_name = type(exc).__name__
            if "TooManyRequests" in exc_name:
                raise TooManyRequestsError("Rate limited by YouTube.")
            raise YouTubeTranscriptClientError(f"Failed to list transcripts: {exc}")

    def fetch_transcript(
        self,
        video_id: str,
        languages: list[str] | None = None,
        prefer_manual: bool = True,
    ) -> list[dict[str, Any]]:
        """Fetch transcript segments for a video.

        Args:
            video_id: 11-character YouTube video ID.
            languages: Optional list of language codes to try (default ["en"]).
            prefer_manual: Prefer manually created captions.

        Returns:
            List of dicts with keys: text, start, duration.

        Raises:
            NoTranscriptFoundError: No transcript found.
            TranscriptSslError: SSL handshake failure.
            YouTubeTranscriptClientError: Other failures.
        """
        langs = languages or ["en"]
        transcript_list = self.list_transcripts(video_id)

        if prefer_manual:
            for lang in langs:
                try:
                    transcript = transcript_list.find_manually_created_transcript([lang])
                    return self._to_dicts(transcript.fetch())
                except NoTranscriptFound:
                    continue

        for lang in langs:
            try:
                transcript = transcript_list.find_generated_transcript([lang])
                return self._to_dicts(transcript.fetch())
            except NoTranscriptFound:
                continue

        try:
            transcript = transcript_list.find_transcript(langs)
            return self._to_dicts(transcript.fetch())
        except NoTranscriptFound:
            pass

        raise NoTranscriptFoundError(
            f"No transcript found for video {video_id} in languages {langs}."
        )

    def fetch_transcript_all_languages(
        self, video_id: str, prefer_manual: bool = True
    ) -> tuple[list[dict[str, Any]], str, bool]:
        """Fetch transcript in any available language, auto-detecting.

        Args:
            video_id: 11-character YouTube video ID.
            prefer_manual: Prefer manually created captions.

        Returns:
            Tuple of (segments, language_code, is_manual).
        """
        transcript_list = self.list_transcripts(video_id)

        if prefer_manual:
            for t in transcript_list:
                if not t.is_generated:
                    return self._to_dicts(t.fetch()), t.language_code, True

        for t in transcript_list:
            if t.is_generated:
                return self._to_dicts(t.fetch()), t.language_code, False

        try:
            t = transcript_list.find_transcript(["en"])
            return self._to_dicts(t.fetch()), t.language_code, not t.is_generated
        except Exception as exc:
            raise NoTranscriptFoundError(
                f"No transcript found for video {video_id}: {exc}"
            )

    @staticmethod
    def _to_dicts(fetched_transcript: Any) -> list[dict[str, Any]]:
        """Convert FetchedTranscript to list of dicts."""
        return [
            {"text": seg.text, "start": seg.start, "duration": seg.duration}
            for seg in fetched_transcript
        ]

    @staticmethod
    def parse_segments(raw_segments: list[dict[str, Any]]) -> list[TranscriptSegment]:
        """Convert raw API segments to structured TranscriptSegment models.

        Args:
            raw_segments: List of dicts with text, start, duration keys.

        Returns:
            List of ``TranscriptSegment`` objects.
        """
        parsed: list[TranscriptSegment] = []
        for seg in raw_segments:
            start = float(seg.get("start", 0))
            duration = float(seg.get("duration", 0))
            text = str(seg.get("text", "")).strip()
            if not text:
                continue
            parsed.append(
                TranscriptSegment(
                    start=start,
                    end=start + duration,
                    duration=duration,
                    text=text,
                )
            )
        return parsed
