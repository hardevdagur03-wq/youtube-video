"""
YouTube CSV Export — FastAPI Application

Architecture
============
- Exports run in a background daemon thread, writing progress + result to disk.
- The export pipeline **streams** data: metadata records are transformed and
  written to the CSV incrementally as they arrive from the API.  This keeps
  memory constant regardless of channel size.
- Stale runs (≥ 1 hour old, incomplete) are cleaned up on startup.

Endpoints
=========
POST /run          Start a new export (returns run_id).
GET  /dashboard/{id}  Legacy Jinja2 dashboard page.
GET  /api/progress/{id}  Poll export progress.
GET  /api/result/{id}    Get export result.
GET  /api/download/{id}  Download the CSV file.
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

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
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

CURRENT_DIR = Path(__file__).resolve().parent
RUNS_DIR = CURRENT_DIR / "runs"
TEMPLATES_DIR = CURRENT_DIR / "templates"
STATIC_DIR = CURRENT_DIR / "static"
FRONTEND_DIST = CURRENT_DIR.parent / "frontend" / "dist"

logger = logging.getLogger("webapp")

jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

_STALE_AGE_SECONDS = 3600  # 1 hour
_RUN_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")


def _safe_run_id(raw: str) -> str | None:
    """Validate run_id to prevent path traversal."""
    if _RUN_ID_PATTERN.match(raw):
        return raw
    return None


def _clean_stale_runs() -> None:
    """Remove incomplete run directories older than _STALE_AGE_SECONDS."""
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
    """Write current progress to disk."""
    with open(run_dir / "progress.json", "w", encoding="utf-8") as f:
        json.dump({"steps": steps, "complete": False}, f)


def _publish_result(run_dir: Path, result: dict) -> None:
    """Write final result to disk."""
    with open(run_dir / "result.json", "w", encoding="utf-8") as f:
        json.dump(result, f)


def _publish_complete(run_dir: Path, steps: list[dict]) -> None:
    """Mark progress as complete."""
    with open(run_dir / "progress.json", "w", encoding="utf-8") as f:
        json.dump({"steps": steps, "complete": True}, f)


def run_pipeline(channel_id: str, limit: int, run_dir: Path) -> None:
    """Execute the full export pipeline.

    Writes CSV incrementally via ``StreamingCSVWriter`` so that memory
    usage is O(batch_size) rather than O(total_videos).

    ``result.json`` is written on **every** outcome (success or failure)
    so the frontend never hangs indefinitely.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    start_time = time.time()
    steps: list[dict] = []

    def step(name: str, status: str, detail: str = "") -> None:
        steps.append({"name": name, "status": status, "detail": detail})
        _publish_progress(run_dir, steps)

    try:
        # ---- 1. Channel Resolution -------------------------------------------
        step("Channel Resolution", "running")
        resolver = ChannelResolver()
        resolved = resolver.resolve(channel_id)
        step("Channel Resolution", "ok", f"Found: {resolved['title']}")

        # ---- 2. Video Discovery ---------------------------------------------
        step("Video Discovery", "running")
        discovery = VideoDiscovery()
        disc_result = discovery.discover(resolved["channel_id"])
        total_discovered = len(disc_result["video_ids"])
        step("Video Discovery", "ok", f"{total_discovered} videos found")

        video_ids = disc_result["video_ids"]
        if limit and 0 < limit < len(video_ids):
            video_ids = video_ids[:limit]
            step("Limit", "ok", f"Using latest {limit} videos")

        # ---- 3. Metadata Fetch + Transform + Export (streaming) -------------
        step("Metadata Fetch", "running")
        total_api_calls = disc_result["total_requests"]
        records_written = 0

        with StreamingCSVWriter(run_dir, "videos.csv") as csv_writer:
            for record in metadata_stream(video_ids):
                # Transform inline
                transformed = _transform_record(record)
                if transformed is None:
                    continue

                # Write to CSV immediately
                csv_writer.write_row(transformed)
                records_written += 1

                # Publish progress every 50 records so the frontend stays updated
                if records_written % 50 == 0:
                    step(
                        "Metadata Fetch",
                        "running",
                        f"{records_written}/{len(video_ids)} records",
                    )

            # Metadata fetch complete — count the batches
            api_calls_meta = math.ceil(len(video_ids) / 50)
            total_api_calls += api_calls_meta

        summary = csv_writer.summary()

        step("Export", "ok", f"{summary['exported']} rows written")

        # ---- 4. Build result -------------------------------------------------
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


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


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


app = FastAPI(title="YouTube CSV Export", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="frontend-assets")


def render(name: str, **context: object) -> HTMLResponse:
    return HTMLResponse(jinja_env.get_template(name).render(**context))


# ---------------------------------------------------------------------------
# Routes — Frontend
# ---------------------------------------------------------------------------


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(FRONTEND_DIST / "index.html"), media_type="text/html")


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
        # Give a meaningful error instead of a bare "File not found"
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if not result.get("success"):
                return {"error": f"Export failed: {result.get('error', 'Unknown error')}"}
            return {"error": "CSV file not found. The export may have been cleaned up."}
        return {"error": "Export not started or still in progress."}

    # Validate the CSV is non-empty
    if csv_path.stat().st_size == 0:
        return {"error": "CSV file is empty. No videos were exported."}

    return FileResponse(str(csv_path), media_type="text/csv", filename="videos.csv")
