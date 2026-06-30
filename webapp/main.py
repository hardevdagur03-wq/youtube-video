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
POST /run              Start a new export (returns run_id).
GET  /dashboard/{id}   Legacy Jinja2 dashboard page.
GET  /api/progress/{id}  Poll export progress.
GET  /api/result/{id}    Get export result.
GET  /api/download/{id}  Download the CSV file.
GET  /{path:path}       SPA catch-all — serves frontend for client-side routing.
"""

import json
import logging
import re
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

from services.channel_resolver import ChannelResolver, ChannelResolverError
from services.data_transformer import DataTransformer, _transform_record
from services.exporter import StreamingCSVWriter, CSVExporter
from services.video_discovery import VideoDiscovery, VideoDiscoveryError
from services.video_metadata import (
    VideoMetadataService,
    VideoMetadataError,
    metadata_stream,
)
from services.youtube_url_parser import YouTubeURLParser
from services.youtube_metadata_service import YouTubeMetadataService

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
                for f in entry.iterdir():
                    f.unlink(missing_ok=True)
                entry.rmdir()
            except OSError as exc:
                logger.warning("Could not remove stale run %s: %s", entry.name, exc)


def _publish_progress(run_dir: Path, steps: list[dict]) -> None:
    with open(run_dir / "progress.json", "w", encoding="utf-8") as f:
        json.dump({"steps": steps, "complete": False}, f)


def _publish_result(run_dir: Path, result: dict) -> None:
    with open(run_dir / "result.json", "w", encoding="utf-8") as f:
        json.dump(result, f)


def _publish_complete(run_dir: Path, steps: list[dict]) -> None:
    with open(run_dir / "progress.json", "w", encoding="utf-8") as f:
        json.dump({"steps": steps, "complete": True}, f)


def run_pipeline(channel_id: str, limit: int, run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    start_time = time.time()
    steps: list[dict] = []

    def step(name: str, status: str, detail: str = "") -> None:
        steps.append({"name": name, "status": status, "detail": detail})
        _publish_progress(run_dir, steps)

    try:
        step("Channel Resolution", "running")
        resolver = ChannelResolver()
        resolved = resolver.resolve(channel_id)
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

        elapsed = time.time() - start_time
        result = {
            "success": True,
            "run_id": run_dir.name,
            "channel_title": resolved["title"],
            "channel_id": resolved["channel_id"],
            "total_videos": summary["exported"],
            "total_discovered": total_discovered,
            "total_api_calls": total_api_calls,
            "file_size_bytes": summary["file_size_bytes"],
            "elapsed_seconds": round(elapsed, 1),
            "steps": steps,
        }
        _publish_result(run_dir, result)
        _publish_complete(run_dir, steps)

        logger.info(
            "Pipeline complete: channel=%s, exported=%d, api_calls=%d, elapsed=%.1fs",
            resolved["channel_id"],
            summary["exported"],
            total_api_calls,
            elapsed,
        )

    except Exception as exc:
        logger.exception("Pipeline failed")
        elapsed = time.time() - start_time
        step("Error", "error", str(exc))
        result = {
            "success": False,
            "run_id": run_dir.name,
            "error": str(exc),
            "elapsed_seconds": round(elapsed, 1),
            "steps": steps,
        }
        _publish_result(run_dir, result)
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
    logger.exception("Unhandled exception on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": (
                "An unexpected error occurred. "
                "Technical details have been logged. Please try again."
            ),
        },
    )


def render(name: str, **context: object) -> HTMLResponse:
    return HTMLResponse(jinja_env.get_template(name).render(**context))


_INDEX_HTML = str(FRONTEND_DIST / "index.html")


def _spa_index() -> FileResponse:
    """Return the SPA index.html for client-side routing."""
    return FileResponse(_INDEX_HTML, media_type="text/html")


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

    Path parameter:
        video_id: 11-character YouTube video ID.

    Query parameters:
        language: Preferred language code (e.g. "en", "es").
        force_refresh: Bypass cache if true.
        allow_whisper: Allow Whisper fallback (default true).

    Returns:
        A ``TranscriptResult``-compatible dict with segments, plain_text, etc.
    """
    service = _get_transcript_service()
    result = service.get_transcript(
        video_id=video_id,
        language=language,
        force_refresh=force_refresh,
        allow_whisper=allow_whisper,
    )
    return result.model_dump()


@app.get("/api/transcript/{video_id}/status")
async def api_transcript_status(video_id: str) -> dict:
    """Check transcript availability without full retrieval.

    Path parameter:
        video_id: 11-character YouTube video ID.

    Returns:
        Dict with availability info for each pipeline stage.
    """
    service = _get_transcript_service()
    return service.get_transcript_status(video_id)


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


@app.post("/run", response_model=None)
async def run(request: Request, channel: str = Form(...), limit: int = Form(0)):
    run_id = uuid.uuid4().hex[:12]
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    Thread(target=run_pipeline, args=(channel.strip(), limit, run_dir), daemon=True).start()
    if request.headers.get("x-spa-request") == "1":
        return {"run_id": run_id}
    return RedirectResponse(url=f"/dashboard/{run_id}", status_code=303)


@app.get("/api/progress/{run_id}")
async def api_progress(run_id: str) -> dict:
    if not _safe_run_id(run_id):
        return {"steps": [], "complete": True, "error": "Invalid run ID"}
    progress_path = RUNS_DIR / run_id / "progress.json"
    if not progress_path.exists():
        return {"steps": [], "complete": False}
    return json.loads(progress_path.read_text(encoding="utf-8"))


@app.get("/api/result/{run_id}")
async def api_result(run_id: str) -> dict:
    if not _safe_run_id(run_id):
        return {"success": False, "error": "Invalid run ID"}
    result_path = RUNS_DIR / run_id / "result.json"
    if not result_path.exists():
        return {"success": False, "error": "Export not ready"}
    return json.loads(result_path.read_text(encoding="utf-8"))


@app.get("/api/download/{run_id}", response_model=None)
async def api_download(run_id: str):
    if not _safe_run_id(run_id):
        return {"error": "Invalid run ID"}

    csv_path = RUNS_DIR / run_id / "videos.csv"
    result_path = RUNS_DIR / run_id / "result.json"

    if not csv_path.exists():
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if not result.get("success"):
                return {"error": f"Export failed: {result.get('error', 'Unknown error')}"}
            return {"error": "CSV file not found. The export may have been cleaned up."}
        return {"error": "Export not started or still in progress."}

    if csv_path.stat().st_size == 0:
        return {"error": "CSV file is empty. No videos were exported."}

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
