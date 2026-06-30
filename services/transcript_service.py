"""Transcript Service — multi-stage transcript retrieval orchestration.

Orchestrates the three-stage fallback pipeline:
    Stage 1: Official manual transcript (YouTube)
    Stage 2: Auto-generated transcript (YouTube)
    Stage 3: Speech-to-text via Whisper (local/API)

Implements the Strategy pattern with dependency injection for
testability and future extensibility.
"""

import logging
import time
from typing import Any

from models.transcript import (
    TranscriptResult,
    TranscriptSource,
    PipelineStep,
)
from interfaces.transcript_provider import TranscriptProvider
from providers.manual_transcript_provider import ManualTranscriptProvider
from providers.auto_transcript_provider import AutoTranscriptProvider
from providers.whisper_provider import WhisperProvider
from repositories.transcript_repository import TranscriptRepository
from exceptions.transcript_errors import (
    TranscriptUnavailableError,
    TranscriptDisabledError,
    TranscriptFetchError,
    AudioDownloadError,
    TranscriptionError,
    InvalidVideoIdError,
)
from utils.text_cleaner import TextCleaner
from utils.read_time import estimate_read_time

logger = logging.getLogger(__name__)


class TranscriptService:
    """Orchestrates the transcript retrieval pipeline.

    Uses a multi-stage fallback pipeline to retrieve the highest-quality
    transcript available. Results are cached via ``TranscriptRepository``.

    Usage::

        service = TranscriptService()
        result = service.get_transcript("dQw4w9WgXcQ")
        if result.success:
            print(result.plain_text[:200])
    """

    def __init__(
        self,
        manual_provider: TranscriptProvider | None = None,
        auto_provider: TranscriptProvider | None = None,
        whisper_provider: TranscriptProvider | None = None,
        repository: TranscriptRepository | None = None,
        text_cleaner: TextCleaner | None = None,
        use_cache: bool = True,
    ) -> None:
        self._manual_provider = manual_provider or ManualTranscriptProvider()
        self._auto_provider = auto_provider or AutoTranscriptProvider()
        self._whisper_provider = whisper_provider
        self._repository = repository or TranscriptRepository()
        self._text_cleaner = text_cleaner or TextCleaner()
        self._use_cache = use_cache

    def _get_whisper_provider(self) -> TranscriptProvider:
        """Lazy-load the Whisper provider (may fail if deps missing)."""
        if self._whisper_provider is None:
            self._whisper_provider = WhisperProvider()
        return self._whisper_provider

    def get_transcript(
        self,
        video_id: str,
        language: str | None = None,
        force_refresh: bool = False,
        allow_whisper: bool = True,
    ) -> TranscriptResult:
        """Retrieve the best available transcript for a video.

        Implements the three-stage fallback pipeline:
        1. Manual transcript (highest quality)
        2. Auto-generated transcript
        3. Whisper speech-to-text (last resort)

        Args:
            video_id: 11-character YouTube video ID.
            language: Preferred language code (e.g. "en", "es").
            force_refresh: If True, bypass cache.
            allow_whisper: If False, skip Stage 3 (Whisper fallback).

        Returns:
            ``TranscriptResult`` with transcript data and pipeline metadata.

        Raises:
            InvalidVideoIdError: If video_id is malformed.
        """
        self._validate_video_id(video_id)

        pipeline_steps: list[dict[str, Any]] = []
        start_time = time.time()

        # Stage 1: Check cache
        if self._use_cache and not force_refresh:
            cached = self._repository.get(video_id)
            if cached is not None:
                logger.info("Returning cached transcript for %s (source=%s)", video_id, cached.source)
                return cached

        # Stage 1: Manual transcript
        step_manual = self._execute_stage(
            "Manual Transcript",
            video_id,
            language,
            self._manual_provider,
            pipeline_steps,
        )
        if step_manual and step_manual.get("status") == "ok":
            result = self._finalize(step_manual["result"], pipeline_steps, start_time)
            self._repository.save(result)
            return result

        # Stage 2: Auto transcript
        step_auto = self._execute_stage(
            "Auto Transcript",
            video_id,
            language,
            self._auto_provider,
            pipeline_steps,
        )
        if step_auto and step_auto.get("status") == "ok":
            result = self._finalize(step_auto["result"], pipeline_steps, start_time)
            self._repository.save(result)
            return result

        # Stage 3: Whisper
        if allow_whisper:
            try:
                whisper_provider = self._get_whisper_provider()
            except ImportError as exc:
                pipeline_steps.append({
                    "name": "Whisper STT",
                    "status": "skipped",
                    "detail": f"Dependencies not available: {exc}",
                })
                whisper_provider = None

            if whisper_provider:
                step_whisper = self._execute_stage(
                    "Whisper STT",
                    video_id,
                    language,
                    whisper_provider,
                    pipeline_steps,
                )
            else:
                step_whisper = None
            if step_whisper and step_whisper.get("status") == "ok":
                result = self._finalize(step_whisper["result"], pipeline_steps, start_time)
                self._repository.save(result)
                return result

        # All stages failed
        pipeline_steps.append({
            "name": "Error",
            "status": "error",
            "detail": "No transcript available from any source.",
        })
        elapsed = round(time.time() - start_time, 2)
        error_result = self._build_error_result(
            video_id,
            pipeline_steps,
            elapsed,
        )
        self._repository.save(error_result)
        return error_result

    def get_transcript_status(self, video_id: str) -> dict[str, Any]:
        """Check transcript availability without full retrieval.

        Args:
            video_id: 11-character YouTube video ID.

        Returns:
            Dict with availability info for each stage.
        """
        result: dict[str, Any] = {
            "video_id": video_id,
            "cached": False,
            "manual_available": False,
            "auto_available": False,
            "whisper_possible": True,
        }

        cached = self._repository.get(video_id)
        if cached is not None:
            result["cached"] = True
            result["source"] = cached.source

        return result

    def _execute_stage(
        self,
        stage_name: str,
        video_id: str,
        language: str | None,
        provider: TranscriptProvider,
        pipeline_steps: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Execute a single pipeline stage.

        Args:
            stage_name: Human-readable stage name.
            video_id: YouTube video ID.
            language: Preferred language.
            provider: The transcript provider for this stage.
            pipeline_steps: Accumulator for pipeline progress.

        Returns:
            Step dict with result on success, or None on failure.
        """
        step: dict[str, Any] = {
            "name": stage_name,
            "status": "running",
            "detail": "",
        }
        pipeline_steps.append(step)

        try:
            transcript = provider.get_transcript(video_id, language=language)
            if transcript.success and transcript.segments:
                step["status"] = "ok"
                step["detail"] = f"{transcript.source.value} ({transcript.language}, {transcript.word_count} words)"
                step["result"] = transcript
                return step

            step["status"] = "error"
            step["detail"] = transcript.error or "No segments returned"
            return step

        except (TranscriptDisabledError) as exc:
            step["status"] = "skipped"
            step["detail"] = str(exc)
            return step

        except (TranscriptUnavailableError, TranscriptFetchError) as exc:
            step["status"] = "skipped"
            step["detail"] = str(exc)
            return step

        except (AudioDownloadError, TranscriptionError) as exc:
            step["status"] = "error"
            step["detail"] = f"{type(exc).__name__}: {exc}"
            return step

        except Exception as exc:
            logger.exception("Unexpected error in stage '%s' for %s", stage_name, video_id)
            step["status"] = "error"
            step["detail"] = f"Unexpected error: {exc}"
            return step

    def _finalize(
        self,
        transcript: TranscriptResult,
        pipeline_steps: list[dict[str, Any]],
        start_time: float,
    ) -> TranscriptResult:
        """Finalize transcript result with pipeline metadata."""
        elapsed = round(time.time() - start_time, 2)

        pipeline_steps.append({
            "name": "Cleaning Transcript",
            "status": "ok",
            "detail": f"{transcript.word_count} words, {transcript.character_count} chars",
        })
        pipeline_steps.append({
            "name": "Ready",
            "status": "ok",
            "detail": f"Retrieved in {elapsed}s from {transcript.source.value}",
        })

        transcript.pipeline_steps = [
            PipelineStep(**s) if isinstance(s, dict) else s
            for s in pipeline_steps
        ]

        return transcript

    def _build_error_result(
        self,
        video_id: str,
        pipeline_steps: list[dict[str, Any]],
        elapsed: float,
    ) -> TranscriptResult:
        """Build a failed TranscriptResult when all stages fail."""
        return TranscriptResult(
            success=False,
            video_id=video_id,
            source=TranscriptSource.MANUAL,
            error="No transcript available from any source. The video may not have captions, or audio download/transcription failed.",
            pipeline_steps=[
                PipelineStep(**s) if isinstance(s, dict) else s
                for s in pipeline_steps
            ],
        )

    @staticmethod
    def _validate_video_id(video_id: str) -> None:
        """Validate YouTube video ID format."""
        if not video_id or not isinstance(video_id, str):
            raise InvalidVideoIdError("Video ID must be a non-empty string.")
        if len(video_id) != 11:
            raise InvalidVideoIdError(
                f"Invalid video ID '{video_id}'. Must be exactly 11 characters."
            )

    def clear_cache(self) -> None:
        """Clear the transcript result cache."""
        self._repository.clear()
        logger.info("Transcript service cache cleared")
