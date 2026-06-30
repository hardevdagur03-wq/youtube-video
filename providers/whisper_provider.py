"""Stage 3: Whisper speech-to-text fallback provider."""

import logging
import os
import time
import tempfile
from pathlib import Path

from models.transcript import (
    TranscriptResult,
    TranscriptSource,
    TranscriptProviderName,
    WhisperProcessingInfo,
    TranscriptSegment,
)
from interfaces.transcript_provider import TranscriptProvider
from interfaces.speech_to_text import SpeechToTextClient
from clients.whisper_client import FasterWhisperClient
from exceptions.transcript_errors import (
    AudioDownloadError,
    TranscriptionError,
    TranscriptCleanupError,
)
from utils.text_cleaner import TextCleaner
from utils.language_detector import LanguageDetector
from utils.read_time import estimate_read_time

logger = logging.getLogger(__name__)

try:
    import yt_dlp

    _HAS_YT_DLP = True
except ImportError:
    _HAS_YT_DLP = False


class WhisperProvider(TranscriptProvider):
    """Stage 3 provider: downloads audio and transcribes with Whisper.

    Used when no YouTube transcript (manual or auto) is available.
    The speech-to-text backend is abstracted via ``SpeechToTextClient``,
    allowing future provider swaps (OpenAI Whisper API, Deepgram, etc.)
    without changing business logic.
    """

    def __init__(
        self,
        stt_client: SpeechToTextClient | None = None,
        text_cleaner: TextCleaner | None = None,
        language_detector: LanguageDetector | None = None,
        temp_dir: str | None = None,
        keep_audio: bool = False,
    ) -> None:
        if not _HAS_YT_DLP:
            raise ImportError(
                "yt-dlp is required for audio download. "
                "Install with: pip install yt-dlp"
            )

        self._stt = stt_client or FasterWhisperClient()
        self._text_cleaner = text_cleaner or TextCleaner()
        self._language_detector = language_detector or LanguageDetector()
        self._temp_dir = temp_dir
        self._keep_audio = keep_audio

    def name(self) -> str:
        return f"Whisper ({self._stt.model_name()})"

    def get_transcript(
        self, video_id: str, language: str | None = None
    ) -> TranscriptResult:
        """Download audio and transcribe with Whisper.

        Pipeline:
            1. Download audio stream via yt-dlp
            2. Extract/convert to WAV
            3. Transcribe with configured STT backend
            4. Parse segments and normalize
            5. Clean up temporary files

        Args:
            video_id: 11-character YouTube video ID.
            language: Optional language hint for transcription.

        Returns:
            ``TranscriptResult`` with whisper-generated transcript.

        Raises:
            AudioDownloadError: If audio cannot be downloaded.
            TranscriptionError: If transcription fails.
        """
        result = TranscriptResult(
            video_id=video_id,
            source=TranscriptSource.WHISPER,
            provider=TranscriptProviderName.FASTER_WHISPER,
        )

        audio_path = None
        download_start = time.time()

        try:
            audio_path = self._download_audio(video_id)
            download_time = time.time() - download_start
            logger.info(
                "Audio downloaded for %s in %.1fs: %s",
                video_id, download_time, audio_path,
            )
        except Exception as exc:
            raise AudioDownloadError(f"Failed to download audio for {video_id}: {exc}")

        try:
            stt_result = self._stt.transcribe(audio_path, language=language)
        except Exception as exc:
            if audio_path and os.path.exists(audio_path):
                self._cleanup_file(audio_path)
            raise TranscriptionError(f"Whisper transcription failed for {video_id}: {exc}")

        segments = [
            TranscriptSegment(
                start=seg.start,
                end=seg.end,
                duration=round(seg.end - seg.start, 2),
                text=seg.text.strip(),
            )
            for seg in stt_result.segments
            if seg.text.strip()
        ]

        segments = self._text_cleaner.clean_segments(segments)

        plain_text = " ".join(seg.text for seg in segments)
        paragraph_text = self._text_cleaner.build_paragraphs(segments)
        word_count = len(plain_text.split())
        char_count = len(plain_text)
        duration = segments[-1].end if segments else 0

        detected_lang = self._language_detector.detect(plain_text)
        final_language = detected_lang.language if detected_lang else (language or stt_result.language or "en")
        final_confidence = detected_lang.confidence if detected_lang else stt_result.language_confidence

        result = TranscriptResult(
            success=True,
            video_id=video_id,
            source=TranscriptSource.WHISPER,
            provider=TranscriptProviderName.FASTER_WHISPER,
            language=final_language,
            language_confidence=final_confidence,
            segments=segments,
            plain_text=plain_text,
            paragraph_text=paragraph_text,
            word_count=word_count,
            character_count=char_count,
            estimated_read_time=estimate_read_time(word_count),
            duration_seconds=duration,
            whisper_info=WhisperProcessingInfo(
                model_name=self._stt.model_name(),
                transcription_duration_seconds=stt_result.processing_time_seconds,
                audio_duration_seconds=stt_result.duration_seconds,
                processing_time_seconds=(
                    stt_result.processing_time_seconds or 0
                ) + (time.time() - download_start),
                language_detected=stt_result.language,
                language_confidence=stt_result.language_confidence,
                word_timestamps=True,
                audio_download_time_seconds=time.time() - download_start,
            ),
            error=None,
        )

        if audio_path and os.path.exists(audio_path) and not self._keep_audio:
            self._cleanup_file(audio_path)

        return result

    def _download_audio(self, video_id: str) -> str:
        """Download audio from YouTube video.

        Args:
            video_id: YouTube video ID.

        Returns:
            Path to downloaded audio file.
        """
        tmp_dir = self._temp_dir or tempfile.mkdtemp(prefix="whisper_")
        output_template = os.path.join(tmp_dir, f"{video_id}.%(ext)s")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                }
            ],
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}",
                    download=True,
                )
                title = info.get("title", "unknown")
                logger.info("Downloaded audio for: %s", title)
        except Exception as exc:
            raise AudioDownloadError(f"yt-dlp download failed: {exc}")

        wav_path = os.path.join(tmp_dir, f"{video_id}.wav")
        if not os.path.isfile(wav_path):
            # Try other extensions
            for ext in (".m4a", ".mp3", ".webm", ".opus"):
                candidate = os.path.join(tmp_dir, f"{video_id}{ext}")
                if os.path.isfile(candidate):
                    wav_path = candidate
                    break
            else:
                raise AudioDownloadError(f"Downloaded audio file not found for {video_id}")

        return wav_path

    @staticmethod
    def _cleanup_file(path: str) -> None:
        """Safely remove a temporary file."""
        try:
            if os.path.isfile(path):
                os.unlink(path)
                parent = os.path.dirname(path)
                if os.path.isdir(parent) and "whisper_" in os.path.basename(parent):
                    try:
                        os.rmdir(parent)
                    except OSError:
                        pass
        except OSError as exc:
            logger.warning("Cleanup warning for %s: %s", path, exc)
