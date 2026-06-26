"""CSV export service for transformed video metadata records."""

import csv
import logging
from pathlib import Path
from typing import Any

from config.settings import settings

logger = logging.getLogger(__name__)

CSV_COLUMNS = [
    "video_id",
    "title",
    "upload_date",
    "views",
    "likes",
    "duration",
    "video_type",
    "video_url",
]

_REQUIRED_FIELDS = {"video_id", "title", "duration", "video_type"}


class CSVExporterError(Exception):
    """Base exception for CSV export errors."""
    pass


class CSVExporter:
    """Exports transformed video metadata records to a CSV file.

    Uses Python's built-in ``csv`` module for proper quoting and escaping.
    Output is UTF-8 encoded.
    """

    def __init__(self, output_dir: Path | str | None = None) -> None:
        self._output_dir = Path(output_dir) if output_dir else settings.output_dir

    def export(
        self,
        records: list[dict[str, Any]],
        filename: str = "videos.csv",
    ) -> dict[str, Any]:
        """Write transformed records to a CSV file.

        Args:
            records: List of transformed video records from Phase 5.
            filename: Output filename (default ``videos.csv``).

        Returns:
            Dictionary with keys:
            - ``filepath``: Absolute path to the written file.
            - ``total_input``: Number of records provided.
            - ``exported``: Number of records successfully written.
            - ``skipped``: Number of records skipped (missing required fields).
            - ``success``: ``True`` if the file was written.
            - ``file_size_bytes``: Size of the written file in bytes.

        Raises:
            CSVExporterError: If the file cannot be written.
        """
        if not records:
            logger.info("No records to export; writing empty CSV.")
            result = self._write_rows([], filename)
            result["total_input"] = 0
            result["exported"] = 0
            result["skipped"] = 0
            return result

        logger.info("Export started: %d record(s)", len(records))

        valid_rows: list[dict[str, Any]] = []
        skipped = 0

        for record in records:
            missing = _REQUIRED_FIELDS - set(record.keys())
            if missing:
                vid = record.get("video_id", "unknown")
                logger.warning("Skipping record %s: missing fields %s", vid, missing)
                skipped += 1
                continue

            if not record.get("video_id"):
                logger.warning("Skipping record with empty video_id")
                skipped += 1
                continue

            row = {col: record.get(col, "") for col in CSV_COLUMNS}
            valid_rows.append(row)

        result = self._write_rows(valid_rows, filename)
        result["total_input"] = len(records)
        result["exported"] = len(valid_rows)
        result["skipped"] = skipped
        return result

    def _write_rows(
        self,
        rows: list[dict[str, Any]],
        filename: str,
    ) -> dict[str, Any]:
        """Write CSV rows to disk."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        filepath = self._output_dir / filename

        try:
            with open(filepath, mode="w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
        except OSError as exc:
            logger.error("Failed to write CSV: %s", exc)
            raise CSVExporterError(
                f"Cannot write CSV to {filepath}: {exc}"
            ) from exc

        file_size = filepath.stat().st_size
        logger.info(
            "CSV exported: %d rows, %d bytes -> %s",
            len(rows),
            file_size,
            filepath,
        )

        return {
            "filepath": str(filepath.resolve()),
            "file_size_bytes": file_size,
            "success": True,
        }
