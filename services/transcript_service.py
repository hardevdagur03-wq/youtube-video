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
    TranscriptProviderName,
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
from clients.youtube_transcript_client import (
    NoTranscriptFoundError as ClientNoTranscriptFoundError,
    TranscriptsDisabledError as ClientTranscriptsDisabledError,
    VideoUnavailableError as ClientVideoUnavailableError,
    TooManyRequestsError as ClientTooManyRequestsError,
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
        import sys
        print(f"[TRANSCRIPT DEBUG] get_transcript called: video_id={video_id}, language={language}, force_refresh={force_refresh}", file=sys.stderr)
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
        import sys
        self._validate_video_id(video_id)

        pipeline_steps: list[dict[str, Any]] = []
        start_time = time.time()

        # Check cache
        if self._use_cache and not force_refresh:
            cached = self._repository.get(video_id)
            if cached is not None:
                logger.info("Returning cached transcript for %s (source=%s)", video_id, cached.source)
                return cached

        # Stage 1: Manual transcript (NEVER throws - trapped as skipped)
        step_manual = self._execute_stage(
            "Manual Transcript",
            video_id,
            language,
            self._manual_provider,
            pipeline_steps,
        )

        # Stage 2: Auto transcript
        step_auto = self._execute_stage(
            "Auto Transcript",
            video_id,
            language,
            self._auto_provider,
            pipeline_steps,
        )

        # Determine best result - prefer manual over auto
        best_step = None
        if step_manual and step_manual.get("status") == "ok":
            best_step = step_manual
            print(f"[TRANSCRIPT DEBUG] Using MANUAL transcript", file=sys.stderr, flush=True)
        elif step_auto and step_auto.get("status") == "ok":
            best_step = step_auto
            print(f"[TRANSCRIPT DEBUG] Using AUTO transcript (manual SKIPPED)", file=sys.stderr, flush=True)

        if best_step:
            result = self._finalize(best_step["result"], pipeline_steps, start_time)
            self._repository.save(result)
            return result

        # Stage 3: Whisper (only if both manual AND auto failed)
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
        print(f"[TRANSCRIPT DEBUG] ALL STAGES FAILED for {video_id}", file=sys.stderr, flush=True)
        return error_result

    def get_all_transcripts(self, video_id: str) -> dict[str, Any]:
        """Retrieve ALL available transcripts separately: manual, auto, translated.

        Never raises exceptions for missing transcripts.
        Returns null for any transcript that is not available.

        Returns:
            Dict with:
                success: bool
                video_id: str
                manual: TranscriptResult | None
                auto: TranscriptResult | None
                pipeline_steps: list[PipelineStep]
                available_languages: list[dict]
        """
        import sys
        self._validate_video_id(video_id)

        pipeline_steps: list[dict[str, Any]] = []
        start_time = time.time()

        result: dict[str, Any] = {
            "success": True,
            "video_id": video_id,
            "manual": None,
            "auto": None,
            "pipeline_steps": [],
            "available_languages": [],
        }

        # Manual
        step_manual = self._execute_stage(
            "Manual Transcript", video_id, None, self._manual_provider, pipeline_steps,
        )
        if step_manual and step_manual.get("status") == "ok":
            result["manual"] = step_manual["result"]
            print(f"[TRANSCRIPT DEBUG] get_all: manual AVAILABLE", file=sys.stderr, flush=True)
        else:
            print(f"[TRANSCRIPT DEBUG] get_all: manual NOT AVAILABLE", file=sys.stderr, flush=True)

        # Auto
        step_auto = self._execute_stage(
            "Auto Transcript", video_id, None, self._auto_provider, pipeline_steps,
        )
        if step_auto and step_auto.get("status") == "ok":
            result["auto"] = step_auto["result"]
            print(f"[TRANSCRIPT DEBUG] get_all: auto AVAILABLE", file=sys.stderr, flush=True)
        else:
            print(f"[TRANSCRIPT DEBUG] get_all: auto NOT AVAILABLE", file=sys.stderr, flush=True)

        # If both failed — overall failure
        if result["manual"] is None and result["auto"] is None:
            result["success"] = False
            pipeline_steps.append({
                "name": "Error",
                "status": "error",
                "detail": "No transcript available from any source.",
            })

        # Available languages from whichever succeeded
        best = result["manual"] or result["auto"]
        if best:
            result["available_languages"] = best.available_languages or []
            result["pipeline_steps"] = pipeline_steps
            # Add finalizing steps
            elapsed = round(time.time() - start_time, 2)
            pipeline_steps.append({
                "name": "Cleaning Transcript",
                "status": "ok",
                "detail": f"{best.word_count} words, {best.character_count} chars",
            })
            pipeline_steps.append({
                "name": "Ready",
                "status": "ok",
                "detail": f"Retrieved in {elapsed}s",
            })
        else:
            result["pipeline_steps"] = pipeline_steps

        print(f"[TRANSCRIPT DEBUG] get_all returning: manual={'YES' if result['manual'] else 'NULL'}, auto={'YES' if result['auto'] else 'NULL'}", file=sys.stderr, flush=True)
        return result

    def get_transcript_status(self, video_id: str) -> dict[str, Any]:
        """Check transcript availability without full retrieval.

        Enumerates ALL available transcripts via the YouTube API and
        returns structured data about each one.

        Args:
            video_id: 11-character YouTube video ID.

        Returns:
            Dict with availability info including every available transcript
            with language, language_code, is_generated, is_translatable.
        """
        result: dict[str, Any] = {
            "video_id": video_id,
            "cached": False,
            "available_transcripts": [],
            "whisper_possible": True,
        }

        cached = self._repository.get(video_id)
        if cached is not None:
            result["cached"] = True
            result["source"] = cached.source

        try:
            available = self._manual_provider._client.list_all_transcripts(video_id)
            result["available_transcripts"] = [
                {
                    "language": t["language"],
                    "language_code": t["language_code"],
                    "is_generated": t["is_generated"],
                    "is_translatable": t["is_translatable"],
                }
                for t in available
            ]
        except Exception as exc:
            logger.warning("Could not enumerate transcripts for %s: %s", video_id, exc)

        return result

    def _execute_stage(
        self,
        stage_name: str,
        video_id: str,
        language: str | None,
        provider: TranscriptProvider,
        pipeline_steps: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        import sys
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
                print(f"[TRANSCRIPT DEBUG] Stage OK: {stage_name} -> {transcript.language}, {transcript.word_count} words", file=sys.stderr, flush=True)
                return step

            step["status"] = "error"
            step["detail"] = transcript.error or "No segments returned"
            print(f"[TRANSCRIPT DEBUG] Stage ERROR (no segments): {stage_name} -> {transcript.error}", file=sys.stderr, flush=True)
            return step

        except Exception as exc:
            exc_type = type(exc).__name__
            print(f"[TRANSCRIPT DEBUG] Stage EXCEPTION: {stage_name} -> {exc_type}: {exc}", file=sys.stderr, flush=True)

            if isinstance(exc, (TranscriptDisabledError, ClientTranscriptsDisabledError)):
                step["status"] = "skipped"
                step["detail"] = str(exc)
                print(f"[TRANSCRIPT DEBUG]   -> classified as SKIPPED (disabled)", file=sys.stderr, flush=True)
                return step

            if isinstance(exc, (TranscriptUnavailableError, TranscriptFetchError,
                               ClientNoTranscriptFoundError, ClientTooManyRequestsError,
                               ClientVideoUnavailableError)):
                step["status"] = "skipped"
                step["detail"] = str(exc)
                print(f"[TRANSCRIPT DEBUG]   -> classified as SKIPPED (unavailable)", file=sys.stderr, flush=True)
                return step

            if isinstance(exc, (AudioDownloadError, TranscriptionError)):
                step["status"] = "error"
                step["detail"] = f"{exc_type}: {exc}"
                print(f"[TRANSCRIPT DEBUG]   -> classified as ERROR (audio/transcription)", file=sys.stderr, flush=True)
                return step

            logger.exception("Unexpected error in stage '%s' for %s", stage_name, video_id)
            step["status"] = "error"
            step["detail"] = f"Unexpected error: {exc}"
            print(f"[TRANSCRIPT DEBUG]   -> classified as ERROR (unexpected)", file=sys.stderr, flush=True)
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

    def translate_transcript(
        self,
        video_id: str,
        target_language: str,
    ) -> TranscriptResult:
        """Get the transcript in a specific language, translating if necessary.

        Uses YouTube's built-in translation to convert the best available
        transcript into the target language. Results are cached per language.

        Args:
            video_id: 11-character YouTube video ID.
            target_language: Language code to translate to (e.g. "en", "hi").

        Returns:
            ``TranscriptResult`` with translated segments and updated language.
        """
        # Check translation cache first
        cached = self._repository.get_translation(video_id, target_language)
        if cached is not None:
            return cached

        # Get original to ensure transcript exists
        original = self.get_transcript(video_id)
        if not original.success:
            return original

        # If already in target language, return as-is
        if original.language == target_language:
            return original

        # Use auto provider's client for translation
        try:
            client = self._auto_provider._client
            available = client.list_all_transcripts(video_id)

            # Look for exact match in target language
            for t_info in available:
                t_obj = t_info.get("_transcript")
                if t_obj and t_obj.language_code == target_language:
                    raw = client._to_dicts(t_obj.fetch())
                    segments = client.parse_segments(raw)
                    segments = self._text_cleaner.clean_segments(segments)
                    plain_text = " ".join(s.text for s in segments)
                    word_count = len(plain_text.split())
                    char_count = len(plain_text)
                    result = TranscriptResult(
                        success=True,
                        video_id=video_id,
                        source=original.source,
                        provider=original.provider,
                        language=target_language,
                        segments=segments,
                        plain_text=plain_text,
                        paragraph_text="\n".join(s.text for s in segments),
                        word_count=word_count,
                        character_count=char_count,
                        estimated_read_time=estimate_read_time(word_count),
                        available_languages=original.available_languages,
                    )
                    self._repository.save_translation(result, target_language)
                    return result

            # Look for translatable transcript
            for t_info in available:
                t_obj = t_info.get("_transcript")
                if t_obj and t_info.get("is_translatable"):
                    translated = t_obj.translate(target_language)
                    raw = client._to_dicts(translated.fetch())
                    segments = client.parse_segments(raw)
                    segments = self._text_cleaner.clean_segments(segments)
                    plain_text = " ".join(s.text for s in segments)
                    word_count = len(plain_text.split())
                    char_count = len(plain_text)
                    result = TranscriptResult(
                        success=True,
                        video_id=video_id,
                        source=original.source,
                        provider=original.provider,
                        language=target_language,
                        translation_source=t_obj.language_code,
                        segments=segments,
                        plain_text=plain_text,
                        paragraph_text="\n".join(s.text for s in segments),
                        word_count=word_count,
                        character_count=char_count,
                        estimated_read_time=estimate_read_time(word_count),
                        available_languages=original.available_languages,
                    )
                    self._repository.save_translation(result, target_language)
                    return result

            # Fallback: return original
            logger.warning("No translatable transcript found for %s to %s", video_id, target_language)
            return original

        except Exception as exc:
            logger.exception("Translation failed for %s to %s: %s", video_id, target_language, exc)
            return original

    def clear_cache(self) -> None:
        """Clear the transcript result cache."""
        self._repository.clear()
        logger.info("Transcript service cache cleared")
