"""
YouTube CSV Export — FastAPI Application

Architecture
============
- Exports run in a background daemon thread, writing progress + result to disk.
- The export pipeline **streams** data: metadata records are transformed and
  written to the CSV incrementally as they arrive from the API.  This keeps
  memory constant regardless of channel size.
- Stale runs (>= 1 hour old, incomplete) are cleaned up on startup.

Endpoints
=========
GET  /api/health          Health check — verifies backend + YouTube API key.
POST /run                 Start a new export (returns run_id).
GET  /dashboard/{id}      Legacy Jinja2 dashboard page.
GET  /api/progress/{id}   Poll export progress.
GET  /api/result/{id}     Get export result.
GET  /api/download/{id}   Download the CSV file.
GET  /{path:path}         SPA catch-all — serves frontend for client-side routing.
"""

import json
import logging
import re
import shutil
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Thread

import ssl

import requests
from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import math

from services.channel_resolver import ChannelResolver, ChannelResolverError, InvalidHandleError
from services.data_transformer import DataTransformer, _transform_record
from services.exporter import StreamingCSVWriter, CSVExporter, CSVExporterError
from services.video_discovery import VideoDiscovery, VideoDiscoveryError
from services.video_metadata import (
    VideoMetadataService,
    VideoMetadataError,
    metadata_stream,
)
from services.youtube_url_parser import YouTubeURLParser
from services.youtube_metadata_service import YouTubeMetadataService
from api.youtube_client import YouTubeClient, YouTubeAPIClientError

CURRENT_DIR = Path(__file__).resolve().parent
RUNS_DIR = CURRENT_DIR / "runs"
TEMPLATES_DIR = CURRENT_DIR / "templates"
STATIC_DIR = CURRENT_DIR / "static"
FRONTEND_DIST = CURRENT_DIR.parent / "frontend" / "dist"

logger = logging.getLogger("webapp")

jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)


_STALE_AGE_SECONDS = 3600  # 1 hour
_RUN_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")


def _safe_run_id(raw: str) -> str | None:
    if _RUN_ID_PATTERN.match(raw):
        return raw
    return None


def _user_friendly_error(msg: str) -> str:
    """Convert raw exception messages into user-friendly error messages.

    Covers all known error categories including network, auth, and API errors.
    """
    lower = msg.lower()
    if "expired" in lower and "api key" in lower:
        return (
            "Your YouTube API key has expired. "
            "Please update the YOUTUBE_API_KEY in your .env file with a valid key from Google Cloud Console."
        )
    if "quota" in lower:
        return "YouTube API quota exceeded. Please try again later or upgrade your API quota."
    if "forbidden" in lower or "403" in msg or "access denied" in lower:
        return "Access to the YouTube API was denied. Please check your API key permissions."
    if "not found" in lower:
        return "The requested channel or video was not found. Check the URL and try again."
    if "403" in msg or "access not configured" in lower:
        return (
            "YouTube API access is not configured. "
            "Please enable the YouTube Data API v3 in Google Cloud Console and ensure your API key has access."
        )
    if any(term in lower for term in ("connection", "timeout", "dns", "failed to fetch", "failed to connect",
                                       "name or service not known", "network is unreachable", "connection refused",
                                       "connection reset", "econnrefused", "econnreset", "ehostunreach",
                                       "eof", "ssl", "tls", "handshake")):
        return "Unable to connect to the YouTube API. Please check your network connection and try again."
    if "unauthorized" in lower or "401" in msg:
        return "API key is invalid or unauthorized. Please check your YOUTUBE_API_KEY in .env."
    if "invalid" in lower and "channel" in lower:
        return msg
    return msg


def _clean_stale_runs() -> None:
    if not RUNS_DIR.exists():
        return
    now = time.time()
    for entry in RUNS_DIR.iterdir():
        if not entry.is_dir():
            continue
        if not _RUN_ID_PATTERN.match(entry.name):
            continue
        result_file = entry / "result.json"
        if result_file.exists():
            continue
        age = now - entry.stat().st_mtime
        if age > _STALE_AGE_SECONDS:
            logger.info("Removing stale run directory: %s (age=%.0fs)", entry.name, age)
            try:
                shutil.rmtree(str(entry), ignore_errors=True)
            except Exception as exc:
                logger.warning("Could not remove stale run %s: %s", entry.name, exc)


def _atomic_write_json(path: Path, data: object) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
        f.flush()
    tmp.replace(path)


def _publish_progress(run_dir: Path, steps: list[dict]) -> None:
    _atomic_write_json(run_dir / "progress.json", {"steps": steps, "complete": False})


def _publish_result(run_dir: Path, result: dict) -> None:
    _atomic_write_json(run_dir / "result.json", result)


def _publish_complete(run_dir: Path, steps: list[dict]) -> None:
    _atomic_write_json(run_dir / "progress.json", {"steps": steps, "complete": True})


def run_pipeline(channel_input: str, limit: int, run_dir: Path) -> None:
    correlation_id = _get_request_id()
    run_dir.mkdir(parents=True, exist_ok=True)
    start_time = time.time()
    steps: list[dict] = []

    def step(name: str, status: str, detail: str = "") -> None:
        elapsed = round(time.time() - start_time, 1)
        steps.append({"name": name, "status": status, "detail": detail, "elapsed": elapsed})
        _publish_progress(run_dir, steps)

    def make_result(success: bool, **extra: object) -> dict:
        elapsed = time.time() - start_time
        return {
            "success": success,
            "run_id": run_dir.name,
            "correlation_id": correlation_id,
            "trace_id": correlation_id,
            "elapsed_seconds": round(elapsed, 1),
            "steps": list(steps),
            **extra,
        }

    try:
        step("Channel Resolution", "running")
        resolver = ChannelResolver()
        resolved = resolver.resolve(channel_input)
        step("Channel Resolution", "ok", f"Found: {resolved['title']}")

        step("Video Discovery", "running")
        discovery = VideoDiscovery()
        disc_result = discovery.discover(resolved["channel_id"])
        total_discovered = len(disc_result["video_ids"])
        step("Video Discovery", "ok", f"{total_discovered} videos found")

        video_ids = disc_result["video_ids"]
        if limit and 0 < limit < len(video_ids):
            video_ids = video_ids[:limit]
            step("Limit", "ok", f"Using latest {limit} videos")

        step("Metadata Fetch", "running")
        total_api_calls = disc_result["total_requests"]
        records_written = 0

        with StreamingCSVWriter(run_dir, "videos.csv") as csv_writer:
            for record in metadata_stream(video_ids):
                transformed = _transform_record(record)
                if transformed is None:
                    continue
                csv_writer.write_row(transformed)
                records_written += 1

                if records_written % 50 == 0:
                    step(
                        "Metadata Fetch",
                        "running",
                        f"{records_written}/{len(video_ids)} records",
                    )

            api_calls_meta = math.ceil(len(video_ids) / 50)
            total_api_calls += api_calls_meta

        summary = csv_writer.summary()

        step("Export", "ok", f"{summary['exported']} rows written")

        elapsed_secs = time.time() - start_time
        result = make_result(
            True,
            channel_title=resolved["title"],
            channel_id=resolved["channel_id"],
            total_videos=summary["exported"],
            total_discovered=total_discovered,
            total_api_calls=total_api_calls,
            file_size_bytes=summary["file_size_bytes"],
        )
        _publish_result(run_dir, result)
        _publish_complete(run_dir, steps)

        logger.info(
            "[%s] Pipeline complete: channel=%s, exported=%d, api_calls=%d, elapsed=%.1fs",
            correlation_id,
            resolved["channel_id"],
            summary["exported"],
            total_api_calls,
            elapsed_secs,
        )

    except (InvalidHandleError, ChannelResolverError) as exc:
        user_msg = _user_friendly_error(str(exc))
        logger.warning("[%s] Channel resolution failed: %s | user_msg=%s", correlation_id, exc, user_msg)
        step("Error", "error", user_msg)
        _publish_result(run_dir, make_result(False, error=user_msg))
        _publish_complete(run_dir, steps)

    except VideoDiscoveryError as exc:
        user_msg = _user_friendly_error(str(exc))
        logger.error("[%s] Video discovery failed: %s | user_msg=%s", correlation_id, exc, user_msg)
        step("Error", "error", user_msg)
        _publish_result(run_dir, make_result(False, error=user_msg))
        _publish_complete(run_dir, steps)

    except VideoMetadataError as exc:
        user_msg = _user_friendly_error(str(exc))
        logger.error("[%s] Metadata fetch failed: %s | user_msg=%s", correlation_id, exc, user_msg)
        step("Error", "error", user_msg)
        _publish_result(run_dir, make_result(False, error=user_msg))
        _publish_complete(run_dir, steps)

    except CSVExporterError as exc:
        user_msg = _user_friendly_error(str(exc))
        logger.error("[%s] CSV export failed: %s | user_msg=%s", correlation_id, exc, user_msg)
        step("Error", "error", user_msg)
        _publish_result(run_dir, make_result(False, error=user_msg))
        _publish_complete(run_dir, steps)

    except Exception as exc:
        logger.exception("[%s] Pipeline failed unexpectedly: %s: %s", correlation_id, type(exc).__name__, exc)
        user_msg = _user_friendly_error(str(exc))
        step("Error", "error", user_msg)
        _publish_result(run_dir, make_result(False, error=user_msg))
        _publish_complete(run_dir, steps)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
    )
    logger.info("Webapp started — cleaning stale runs")
    _clean_stale_runs()
    yield


app = FastAPI(title="YouTube Export Tool v2", lifespan=lifespan)

# CORS middleware — allows cross-origin requests in development/proxy setups
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="frontend-assets")


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(ssl.SSLError)
async def ssl_error_handler(request: Request, exc: ssl.SSLError) -> JSONResponse:
    logger.error("SSL error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={
            "success": False,
            "error": (
                "Unable to connect securely to the service. "
                "The server closed the connection during the SSL/TLS handshake. "
                "Please try again in a few moments."
            ),
        },
    )


@app.exception_handler(requests.exceptions.SSLError)
async def requests_ssl_error_handler(request: Request, exc: requests.exceptions.SSLError) -> JSONResponse:
    logger.error("requests SSL error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={
            "success": False,
            "error": (
                "Unable to connect securely to the service. "
                "Please try again in a few moments."
            ),
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all exception handler — logs the error and returns a user-friendly message."""
    import uuid
    rid = uuid.uuid4().hex[:8]
    logger.exception("[%s] Unhandled exception on %s %s: %s: %s",
                    rid, request.method, request.url.path, type(exc).__name__, exc)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": (
                "An unexpected error occurred. "
                "Technical details have been logged. Please try again."
            ),
            "trace_id": rid,
            "stage": request.url.path.split("/")[-1] if "/" in request.url.path else "unknown",
        },
    )


def _verify_youtube_api_key() -> tuple[bool, str]:
    """Verify the YouTube API key is configured and not a placeholder."""
    from config.settings import is_youtube_api_key_valid
    return is_youtube_api_key_valid()


# ---------------------------------------------------------------------------
# Generate a request ID for each request
# ---------------------------------------------------------------------------

import contextvars

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


def _get_request_id() -> str:
    rid = _request_id_var.get()
    if not rid:
        rid = uuid.uuid4().hex[:8]
        _request_id_var.set(rid)
    return rid


@app.middleware("http")
async def add_request_id_middleware(request: Request, call_next):
    rid = uuid.uuid4().hex[:8]
    _request_id_var.set(rid)
    start_time = time.time()
    response = await call_next(request)
    elapsed = round(time.time() - start_time, 3)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Elapsed-Ms"] = str(int(elapsed * 1000))
    return response


def render(name: str, **context: object) -> HTMLResponse:
    return HTMLResponse(jinja_env.get_template(name).render(**context))


_INDEX_HTML = str(FRONTEND_DIST / "index.html")


def _spa_index() -> FileResponse:
    """Return the SPA index.html for client-side routing."""
    return FileResponse(_INDEX_HTML, media_type="text/html")


# ---------------------------------------------------------------------------
# Health Check — verify backend and YouTube API key
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def api_health():
    """Health check endpoint.

    Verifies:
    1. Backend is reachable
    2. YouTube API key is configured
    3. YouTube API key is not a placeholder

    Returns:
        JSON with ``status``, ``youtube_api_key_configured``, and ``version``.
    """
    rid = _get_request_id()
    key_ok, key_error = _verify_youtube_api_key()
    status = "ok" if key_ok else "degraded"
    logger.info("[%s] Health check: status=%s, key_ok=%s", rid, status, key_ok)
    return {
        "status": status,
        "youtube_api_key_configured": key_ok,
        "youtube_api_key_error": key_error if not key_ok else None,
        "version": "2.0",
        "request_id": rid,
    }


# ---------------------------------------------------------------------------
# SPA Routes — served by the React frontend
# ---------------------------------------------------------------------------


@app.get("/")
async def index() -> FileResponse:
    return _spa_index()


@app.get("/metadata")
async def spa_metadata() -> FileResponse:
    return _spa_index()


@app.get("/blog")
async def spa_blog() -> FileResponse:
    return _spa_index()


@app.get("/transcript")
async def spa_transcript() -> FileResponse:
    return _spa_index()


@app.get("/analysis")
async def spa_analysis() -> FileResponse:
    return _spa_index()


# ---------------------------------------------------------------------------
# Routes — API / URL Validation
# ---------------------------------------------------------------------------


_url_parser = YouTubeURLParser()
_metadata_service = YouTubeMetadataService()
_transcript_service = None


def _get_transcript_service():
    global _transcript_service
    if _transcript_service is None:
        from services.transcript_service import TranscriptService
        _transcript_service = TranscriptService()
    return _transcript_service


@app.get("/api/validate-url")
async def api_validate_url(url: str = "") -> dict:
    """Validate a YouTube URL and return structured parse result.

    Query parameter:
        url: The YouTube video URL to validate.

    Returns:
        A ``VideoURLResult``-compatible dict with ``valid``, ``video_id``,
        ``normalized_url``, ``url_type``, ``original_url``, and ``error``.
    """
    result = _url_parser.parse(url)
    return result.model_dump()


# ---------------------------------------------------------------------------
# Routes — API / Video Metadata
# ---------------------------------------------------------------------------


@app.get("/api/video-metadata/{video_id}")
async def api_video_metadata(video_id: str) -> dict:
    """Retrieve complete metadata for a YouTube video.

    Path parameter:
        video_id: 11-character YouTube video ID.

    Returns:
        A ``VideoMetadataResponse``-compatible dict.
    """
    result = _metadata_service.get_metadata(video_id)
    return result.model_dump()


# ---------------------------------------------------------------------------
# Routes — API / Transcript
# ---------------------------------------------------------------------------


@app.get("/api/transcript/{video_id}")
async def api_transcript(
    video_id: str,
    language: str | None = None,
    force_refresh: bool = False,
    allow_whisper: bool = True,
) -> dict:
    """Retrieve the best available transcript for a YouTube video.

    Implements a three-stage fallback pipeline:
        1. Manual transcript (human-created captions)
        2. Auto-generated transcript
        3. Whisper speech-to-text (if allow_whisper=true)
    """
    import uuid
    rid = uuid.uuid4().hex[:8]
    logger.info("[%s] Transcript request: video_id=%s, language=%s, whisper=%s", rid, video_id, language, allow_whisper)
    try:
        service = _get_transcript_service()
        result = service.get_transcript(
            video_id=video_id,
            language=language,
            force_refresh=force_refresh,
            allow_whisper=allow_whisper,
        )
        logger.info("[%s] Transcript result: success=%s, source=%s, segments=%d, error=%s",
                    rid, result.success, result.source.value if result.success else "N/A",
                    len(result.segments) if result.segments else 0, result.error)
        return result.model_dump()
    except Exception as exc:
        logger.exception("[%s] Transcript fetch failed for video_id=%s: %s: %s",
                        rid, video_id, type(exc).__name__, exc)
        raise


@app.get("/api/transcript/{video_id}/all")
async def api_transcript_all(video_id: str) -> dict:
    """Retrieve ALL available transcripts separately: manual, auto, translated.

    Returns structured response with separate transcript objects:
        {
            "success": true,
            "video_id": "...",
            "manual": TranscriptResult | null,
            "auto": TranscriptResult | null,
            "pipeline_steps": [...],
            "available_languages": [...]
        }

    Never throws for missing manual captions — returns manual: null instead.
    """
    import sys
    rid = uuid.uuid4().hex[:8]
    print(f"[API DEBUG] /api/transcript/{video_id}/all called", file=sys.stderr, flush=True)
    service = _get_transcript_service()
    result = service.get_all_transcripts(video_id)
    print(f"[API DEBUG] Response: success={result['success']}, manual={'YES' if result.get('manual') else 'NULL'}, auto={'YES' if result.get('auto') else 'NULL'}", file=sys.stderr, flush=True)
    return result


@app.get("/api/transcript/{video_id}/status")
async def api_transcript_status(video_id: str) -> dict:
    """Check transcript availability without full retrieval.

    Enumerates ALL available transcripts with full metadata.

    Path parameter:
        video_id: 11-character YouTube video ID.

    Returns:
        Dict with ``available_transcripts`` list (language, code, generated,
        translatable) and other status info.
    """
    service = _get_transcript_service()
    return service.get_transcript_status(video_id)


@app.get("/api/transcript/{video_id}/translate/{target_language}")
async def api_translate_transcript(video_id: str, target_language: str) -> dict:
    """Translate a cached transcript to a target language.

    Uses YouTube's built-in translation to convert the best available
    transcript into the target language. Results are cached per language.

    Path parameters:
        video_id: 11-character YouTube video ID.
        target_language: Language code (e.g. "en", "hi").

    Returns:
        ``TranscriptResult``-compatible dict with translated segments.
    """
    import uuid
    rid = uuid.uuid4().hex[:8]
    logger.info("[%s] Translate request: video_id=%s, target=%s", rid, video_id, target_language)
    try:
        service = _get_transcript_service()
        result = service.translate_transcript(
            video_id=video_id,
            target_language=target_language,
        )
        logger.info("[%s] Translate result: success=%s, language=%s, segments=%d",
                    rid, result.success, result.language,
                    len(result.segments) if result.segments else 0)
        return result.model_dump()
    except Exception as exc:
        logger.exception("[%s] Translation failed for %s to %s: %s: %s",
                        rid, video_id, target_language, type(exc).__name__, exc)
        raise


@app.get("/api/transcript/{video_id}/list-all")
async def api_transcript_list_all(video_id: str) -> dict:
    """List ALL available transcripts for a video with full metadata.

    Path parameter:
        video_id: 11-character YouTube video ID.

    Returns:
        Dict with ``available_transcripts`` list, each containing:
        language, language_code, is_generated, is_translatable.
    """
    import uuid
    rid = uuid.uuid4().hex[:8]
    logger.info("[%s] List-all-transcripts request: video_id=%s", rid, video_id)
    try:
        service = _get_transcript_service()
        result = service.get_transcript_status(video_id)
        return result
    except Exception as exc:
        logger.exception("[%s] Failed to list transcripts for %s: %s: %s",
                        rid, video_id, type(exc).__name__, exc)
        return {
            "success": False,
            "video_id": video_id,
            "error": str(exc),
            "trace_id": rid,
        }


# ---------------------------------------------------------------------------
# Routes — API / Blog Review (Phase 9)
# ---------------------------------------------------------------------------


_review_engine = None


def _get_review_engine():
    global _review_engine
    if _review_engine is None:
        from review.engine import ReviewEngine
        _review_engine = ReviewEngine()
    return _review_engine


@app.post("/api/review")
async def api_review_blog(request: Request) -> dict:
    """Run a comprehensive quality review on an AI-generated blog.

    Accepts the full blog content and metadata, runs all validators,
    and returns a detailed quality report with scores, issues, and
    actionable recommendations.

    JSON body:
        {
            "blog_title": "...",
            "primary_keyword": "...",
            "secondary_keywords": [...],
            "target_audience": "...",
            "search_intent": "...",
            "meta_title": "...",
            "meta_description": "...",
            "content": "... full markdown or plain text ...",
            "faq": [{"question": "...", "answer": "..."}],
            "internal_links": [{"anchor": "...", "url": "..."}],
            "external_links": [{"anchor": "...", "url": "..."}],
            "images": [{"alt": "...", "url": "..."}]
        }

    Returns:
        {
            "success": true,
            "report": { ... QualityReport ... }
        }
    """
    import json
    rid = uuid.uuid4().hex[:8]
    logger.info("[%s] Blog review request received", rid)

    body = await request.json()
    from models.blog_review import BlogReviewRequest
    req = BlogReviewRequest(**body)

    engine = _get_review_engine()
    response = engine.review(req)

    result = json.loads(response.model_dump_json())
    logger.info("[%s] Review complete: score=%.1f, decision=%s",
                rid, (response.report.overall_score if response.report else 0),
                (response.report.publish_decision.value if response.report else "N/A"))
    return result


# ---------------------------------------------------------------------------
# Routes — API / Transcript Processing (Phase 5)
# ---------------------------------------------------------------------------


_transcript_processor = None


def _get_transcript_processor():
    global _transcript_processor
    if _transcript_processor is None:
        from services.transcript_processor import TranscriptProcessor
        _transcript_processor = TranscriptProcessor()
    return _transcript_processor


@app.post("/api/transcript/{video_id}/process")
async def api_process_transcript(
    video_id: str,
    remove_fillers: bool = False,
) -> dict:
    """Process a raw transcript into clean, AI-ready content.

    Fetches the transcript via GET /api/transcript/{video_id}, then runs
    the multi-stage processing pipeline.

    Query parameters:
        remove_fillers: If true, remove filler words.

    Returns:
        ``ProcessingResult``-compatible dict.
    """
    import json
    from fastapi import HTTPException

    transcript_service = _get_transcript_service()
    transcript = transcript_service.get_transcript(video_id)

    if not transcript.success:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": transcript.error or "No transcript available.",
            },
        )

    processor = _get_transcript_processor()
    result = processor.process(
        segments=transcript.segments,
        video_id=video_id,
        remove_fillers=remove_fillers,
    )
    return json.loads(result.model_dump_json())


@app.post("/api/process-transcript")
async def api_process_transcript_direct(
    request: Request,
) -> dict:
    """Process transcript segments passed in the request body.

    JSON body::

        {
            "segments": [{"text": "...", "start": 0.0, "duration": 5.0}, ...],
            "video_id": "dQw4w9WgXcQ",
            "remove_fillers": false
        }
    """
    import json
    from fastapi import HTTPException

    body = await request.json()
    segments = body.get("segments", [])
    vid = body.get("video_id", "")
    remove = body.get("remove_fillers", False)

    if not segments:
        raise HTTPException(status_code=400, detail={
            "success": False,
            "error": "No segments provided.",
        })

    processor = _get_transcript_processor()
    result = processor.process(
        segments=segments,
        video_id=vid,
        remove_fillers=remove,
    )
    return json.loads(result.model_dump_json())


# ---------------------------------------------------------------------------
# Routes — API / Content Analysis (Phase 6)
# ---------------------------------------------------------------------------


_content_analysis_service = None


def _get_content_analysis_service():
    global _content_analysis_service
    if _content_analysis_service is None:
        from services.content_analysis_service import ContentAnalysisService
        _content_analysis_service = ContentAnalysisService()
    return _content_analysis_service


@app.get("/api/analyze/{video_id}")
async def api_analyze_transcript(
    video_id: str,
    force_refresh: bool = False,
) -> dict:
    """Analyze a video's transcript with the AI Content Analysis Engine.

    Fetches the transcript (via Phase 4/5), processes it if needed,
    then runs the full AI content analysis pipeline.

    Path parameter:
        video_id: 11-character YouTube video ID.

    Query parameters:
        force_refresh: Bypass analysis cache if true.

    Returns:
        ``ContentAnalysisResult``-compatible dict with full semantic intelligence.
    """
    import json
    from fastapi import HTTPException

    transcript_service = _get_transcript_service()
    transcript = transcript_service.get_transcript(video_id)

    if not transcript.success:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": transcript.error or "No transcript available for analysis.",
            },
        )

    processor = _get_transcript_processor()
    processed = processor.process(
        segments=transcript.segments,
        video_id=video_id,
    )

    if not processed.success:
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "error": processed.error or "Failed to process transcript for analysis.",
            },
        )

    meta_service = _metadata_service
    metadata = meta_service.get_metadata(video_id) if video_id else None
    video_stats = metadata.video.statistics.model_dump() if metadata and metadata.success and metadata.video else None
    channel_info = metadata.video.channel.model_dump() if metadata and metadata.success and metadata.video else None
    lang_info = processed.language.model_dump() if processed.language else None

    service = _get_content_analysis_service()
    result = service.analyze(
        transcript=processed.clean_transcript,
        video_id=video_id,
        metadata=metadata.model_dump() if metadata else None,
        video_statistics=video_stats,
        channel_info=channel_info,
        language_info=lang_info,
        force_refresh=force_refresh,
    )
    return json.loads(result.model_dump_json())


@app.post("/api/analyze")
async def api_analyze_direct(request: Request) -> dict:
    """Analyze a transcript passed directly in the request body.

    JSON body::

        {
            "video_id": "dQw4w9WgXcQ",
            "transcript": "... clean transcript text ...",
            "metadata": {...},
            "video_statistics": {...},
            "channel_info": {...},
            "language_info": {...},
            "force_refresh": false,
            "llm_provider": null,
            "llm_model": null
        }
    """
    import json
    from fastapi import HTTPException
    from schemas.analysis_response import AnalyzeTranscriptRequest

    body = await request.json()
    req = AnalyzeTranscriptRequest(**body)

    service = _get_content_analysis_service()
    result = service.analyze(
        transcript=req.transcript,
        video_id=req.video_id,
        metadata=req.metadata,
        video_statistics=req.video_statistics,
        channel_info=req.channel_info,
        language_info=req.language_info,
        force_refresh=req.force_refresh,
        llm_provider=req.llm_provider,
        llm_model=req.llm_model,
    )
    return json.loads(result.model_dump_json())


# ---------------------------------------------------------------------------
# Routes — API / Blog Generation (Phase 6)
# ---------------------------------------------------------------------------


_blog_service = None


def _get_blog_service():
    global _blog_service
    if _blog_service is None:
        from modules.blog.blog_service import BlogGenerationService
        _blog_service = BlogGenerationService()
    return _blog_service


@app.get("/api/blog/{video_id}")
async def api_generate_blog(
    video_id: str,
    force_refresh: bool = False,
) -> dict:
    """Generate a complete SEO blog post from a YouTube video.

    Consumes all prior pipeline phases:
        1. Transcript retrieval (Phase 4)
        2. Transcript processing (Phase 5)
        3. AI content analysis (Phase 6)

    Path parameter:
        video_id: 11-character YouTube video ID.

    Query parameters:
        force_refresh: Bypass blog cache if true.

    Returns:
        ``BlogGenerationResult``-compatible dict with full blog content.
    """
    import json
    from fastapi import HTTPException

    transcript_service = _get_transcript_service()
    transcript = transcript_service.get_transcript(video_id)

    if not transcript.success:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": transcript.error or "No transcript available for blog generation.",
            },
        )

    processor = _get_transcript_processor()
    processed = processor.process(
        segments=transcript.segments,
        video_id=video_id,
    )

    if not processed.success:
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "error": processed.error or "Failed to process transcript for blog.",
            },
        )

    meta_service = _metadata_service
    metadata = meta_service.get_metadata(video_id) if video_id else None
    video_stats = metadata.video.statistics.model_dump() if metadata and metadata.success and metadata.video else None
    channel_info_data = metadata.video.channel.model_dump() if metadata and metadata.success and metadata.video else None
    lang_info = processed.language.model_dump() if processed.language else None

    analysis_service = _get_content_analysis_service()
    analysis = analysis_service.analyze(
        transcript=processed.clean_transcript,
        video_id=video_id,
        metadata=metadata.model_dump() if metadata else None,
        video_statistics=video_stats,
        channel_info=channel_info_data,
        language_info=lang_info,
    )

    packaged_metadata = {}
    if metadata and metadata.success and metadata.video:
        v = metadata.video
        packaged_metadata = {
            "title": getattr(v, "title", ""),
            "description": getattr(v, "description", ""),
            "channel": getattr(v, "channel", None).name if getattr(v, "channel", None) else "",
            "channel_title": getattr(v, "channel", None).name if getattr(v, "channel", None) else "",
            "published_date": str(getattr(v, "published_at", "")),
            "duration": str(getattr(v, "duration", "")),
            "tags": list(getattr(v, "tags", []) or []),
            "category": "",
        }

    service = _get_blog_service()
    result = service.generate(
        transcript=processed.clean_transcript,
        video_id=video_id,
        metadata=packaged_metadata,
        analysis=json.loads(analysis.model_dump_json()),
        force_refresh=force_refresh,
    )
    return json.loads(result.model_dump_json())


@app.post("/api/blog")
async def api_generate_blog_direct(request: Request) -> dict:
    """Generate a blog post from pre-computed context passed directly.

    JSON body::

        {
            "video_id": "dQw4w9WgXcQ",
            "transcript": "... clean transcript text ...",
            "metadata": {...},
            "analysis": {...},
            "llm_provider": null,
            "llm_model": null
        }
    """
    import json
    from fastapi import HTTPException
    from models.blog_generation import BlogGenerationRequest

    body = await request.json()
    req = BlogGenerationRequest(**body)

    service = _get_blog_service()
    result = service.generate(
        transcript=req.transcript,
        video_id=req.video_id,
        metadata=req.metadata,
        analysis=req.analysis,
        llm_provider=req.llm_provider,
        llm_model=req.llm_model,
    )
    return json.loads(result.model_dump_json())


# ---------------------------------------------------------------------------
# Routes — API / SEO Optimization (Phase 8)
# ---------------------------------------------------------------------------


_seo_service = None


def _get_seo_service():
    global _seo_service
    if _seo_service is None:
        from modules.seo.seo_service import SEOService
        _seo_service = SEOService()
    return _seo_service


@app.post("/api/seo")
async def api_seo_optimize(request: Request) -> dict:
    """Run SEO optimization on a generated blog post.

    JSON body::

        {
            "video_id": "dQw4w9WgXcQ",
            "blog": { ... BlogResult dict ... },
            "metadata": { ... optional ... },
            "analysis": { ... optional ... },
            "llm_provider": null,
            "llm_model": null
        }

    Returns:
        ``SEOOptimizationResult`` with full SEO package.
    """
    import json
    from models.seo_package import SEORequest

    body = await request.json()
    req = SEORequest(**body)

    service = _get_seo_service()
    result = service.optimize(
        blog_data=req.blog,
        video_id=req.video_id,
        metadata=req.metadata,
        analysis=req.analysis,
        llm_provider=req.llm_provider,
        llm_model=req.llm_model,
    )
    return json.loads(result.model_dump_json())


@app.post("/api/seo/pipeline")
async def api_seo_full_pipeline(request: Request) -> dict:
    """Full pipeline: generate blog then run SEO optimization.

    JSON body::

        {
            "video_id": "dQw4w9WgXcQ",
            "transcript": "...",
            "metadata": {...},
            "analysis": {...},
            "llm_provider": null,
            "llm_model": null
        }

    Returns:
        Combined blog + SEO package result.
    """
    import json
    from models.blog_generation import BlogGenerationRequest
    from models.seo_package import SEOOptimizationResult

    body = await request.json()
    req = BlogGenerationRequest(**body)

    blog_service = _get_blog_service()
    blog_result = blog_service.generate(
        transcript=req.transcript,
        video_id=req.video_id,
        metadata=req.metadata,
        analysis=req.analysis,
        llm_provider=req.llm_provider,
        llm_model=req.llm_model,
    )

    if not blog_result.success:
        return json.loads(blog_result.model_dump_json())

    seo_service = _get_seo_service()
    seo_result = seo_service.optimize(
        blog_data=json.loads(blog_result.model_dump_json()).get("blog", {}),
        video_id=req.video_id,
        metadata=req.metadata,
        analysis=req.analysis,
        llm_provider=req.llm_provider,
        llm_model=req.llm_model,
    )

    return {
        "success": True,
        "video_id": req.video_id,
        "blog": json.loads(blog_result.model_dump_json()).get("blog"),
        "seo_package": json.loads(seo_result.model_dump_json()).get("seo_package"),
    }


# ---------------------------------------------------------------------------
# Routes — API / Export (Phase 10)
# ---------------------------------------------------------------------------


_export_engine = None


def _get_export_engine():
    global _export_engine
    if _export_engine is None:
        from export.engine import ExportEngine
        _export_engine = ExportEngine()
    return _export_engine


@app.post("/api/export")
async def api_export(request: Request) -> dict:
    """Export a blog to multiple formats.

    Accepts blog content and metadata, generates Markdown, HTML, DOCX,
    and/or PDF files, and returns download URLs.

    JSON body:
        BlogExportRequest-compatible dict with all blog fields.

    Returns:
        ExportResult with generated file metadata and download URLs.
    """
    import json
    rid = uuid.uuid4().hex[:8]
    logger.info("[%s] Export request received", rid)

    body = await request.json()
    from models.blog_export import ExportRequest
    req = ExportRequest(**body)

    engine = _get_export_engine()
    result = engine.export(req)

    # Validate each file
    from export.validator import ExportValidator
    validator = ExportValidator()
    export_dir = Path(__file__).resolve().parent.parent / "exports" / result.export_id
    for ef in result.generated_files:
        filepath = export_dir / ef.filename
        ef = validator.validate(filepath, ef)

    response = json.loads(result.model_dump_json())
    logger.info("[%s] Export complete: %d files, %.1fms",
                rid, result.file_count, result.execution_time_ms)
    return response


@app.get("/api/export/download/{filename:path}")
async def api_export_download(filename: str) -> FileResponse:
    """Download an exported file.

    Path parameter:
        filename: File name (e.g. 'blog.md') or 'exp_xxx.zip'.
    """
    rid = uuid.uuid4().hex[:8]
    from export.engine import EXPORT_DIR

    filepath = EXPORT_DIR / filename
    # Also check subdirectories
    if not filepath.exists():
        for sub in EXPORT_DIR.iterdir():
            if sub.is_dir():
                candidate = sub / filename
                if candidate.exists():
                    filepath = candidate
                    break

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")

    mime_map = {
        ".md": "text/markdown",
        ".html": "text/html",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pdf": "application/pdf",
        ".zip": "application/zip",
    }
    mime = mime_map.get(filepath.suffix.lower(), "application/octet-stream")
    logger.info("[%s] Download: %s (%s)", rid, filename, mime)
    return FileResponse(str(filepath), media_type=mime, filename=filepath.name)


@app.get("/api/blog/{video_id}/export-ready")
async def api_export_ready(video_id: str) -> dict:
    """Check if a blog is ready for export and return export data.

    Path parameter:
        video_id: 11-character YouTube video ID.

    Returns:
        Dict with export-ready flag and blog data if available.
    """
    try:
        from repositories.blog_repository import BlogRepository
        repo = BlogRepository()
        blog_data = repo.get(video_id)
        if blog_data:
            from models.blog_generation import BlogGenerationResult
            blog = BlogGenerationResult(**blog_data)
            if blog.success and blog.blog:
                return {
                    "success": True,
                    "ready": True,
                    "blog": blog.model_dump(),
                }
        return {"success": True, "ready": False, "blog": None}
    except Exception as exc:
        logger.exception("Export readiness check failed: %s", exc)
        return {"success": False, "ready": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Routes — Dashboard
# ---------------------------------------------------------------------------


@app.get("/dashboard/{run_id}")
async def dashboard(request: Request, run_id: str) -> HTMLResponse:
    if not _safe_run_id(run_id):
        return render("error.html", request=request, message="Invalid run ID")
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        return render("error.html", request=request, message="Run not found")
    return render("dashboard.html", request=request, run_id=run_id)


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------


@app.post("/run")
async def run(request: Request, channel: str = Form(default=""), limit: int = Form(default=0)):
    rid = _get_request_id()

    # Validate channel input is not empty
    channel_stripped = channel.strip()
    if not channel_stripped:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "Channel identifier cannot be empty. Please enter a YouTube channel URL, handle, or ID.",
                "trace_id": rid,
            },
        )

    # Verify YouTube API key before starting pipeline
    key_ok, key_error = _verify_youtube_api_key()
    if not key_ok:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": key_error,
                "trace_id": rid,
            },
        )

    run_id = uuid.uuid4().hex[:12]
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    logger.info("[%s] Starting export pipeline: channel=%s, limit=%d, run_id=%s", rid, channel_stripped, limit, run_id)
    Thread(target=run_pipeline, args=(channel_stripped, limit, run_dir), daemon=True).start()
    if request.headers.get("x-spa-request") == "1":
        return {"run_id": run_id, "trace_id": rid}
    return RedirectResponse(url=f"/dashboard/{run_id}", status_code=303)


@app.get("/api/progress/{run_id}")
async def api_progress(run_id: str) -> dict:
    rid = _get_request_id()
    if not _safe_run_id(run_id):
        return {"steps": [], "complete": True, "error": "Invalid run ID", "trace_id": rid}
    progress_path = RUNS_DIR / run_id / "progress.json"
    if not progress_path.exists():
        return {"steps": [], "complete": False, "trace_id": rid}
    data = json.loads(progress_path.read_text(encoding="utf-8"))
    data["trace_id"] = rid
    return data


@app.get("/api/result/{run_id}")
async def api_result(run_id: str) -> dict:
    rid = _get_request_id()
    if not _safe_run_id(run_id):
        return {"success": False, "error": "Invalid run ID", "trace_id": rid}
    result_path = RUNS_DIR / run_id / "result.json"
    if not result_path.exists():
        return {"success": False, "error": "Export not ready", "trace_id": rid}
    data = json.loads(result_path.read_text(encoding="utf-8"))
    data["trace_id"] = rid
    return data


@app.get("/api/download/{run_id}", response_model=None)
async def api_download(run_id: str):
    rid = _get_request_id()
    if not _safe_run_id(run_id):
        return JSONResponse(status_code=400, content={"success": False, "error": "Invalid run ID", "trace_id": rid})

    csv_path = RUNS_DIR / run_id / "videos.csv"
    result_path = RUNS_DIR / run_id / "result.json"

    if not csv_path.exists():
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if not result.get("success"):
                return JSONResponse(
                    status_code=422,
                    content={"success": False, "error": f"Export failed: {result.get('error', 'Unknown error')}", "trace_id": rid},
                )
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "CSV file not found. The export may have been cleaned up.", "trace_id": rid},
            )
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "Export not started or still in progress.", "trace_id": rid},
        )

    if csv_path.stat().st_size == 0:
        return JSONResponse(
            status_code=422,
            content={"success": False, "error": "CSV file is empty. No videos were exported.", "trace_id": rid},
        )

    return FileResponse(str(csv_path), media_type="text/csv", filename="videos.csv")


# ---------------------------------------------------------------------------
# Catch-all — serve SPA for client-side routing
# ---------------------------------------------------------------------------


@app.api_route("/{path:path}", methods=["GET"])
async def spa_catch_all(path: str) -> FileResponse:
    """Serve SPA index.html for client-side routing (all unmatched GET paths)."""
    if path.startswith("api") or path.startswith("dashboard"):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return _spa_index()
