"""Input validation for pipeline ingestion."""

from __future__ import annotations

from pathlib import Path


class IngestValidationError(ValueError):
    """Raised when an ingest input fails validation."""


def validate_input_mp4(input_path: str) -> Path:
    """Validate an input video path and return a normalized Path."""
    path = Path(input_path).expanduser()

    if not path.exists():
        raise IngestValidationError(
            f"Input file was not found: {path}. "
            "Provide an existing local .mp4 path, e.g. --input ./video.mp4."
        )
    if not path.is_file():
        raise IngestValidationError(
            f"Input path is not a file: {path}. "
            "Provide a direct path to a .mp4 file."
        )
    if path.suffix.lower() != ".mp4":
        raise IngestValidationError(
            f"Unsupported file extension '{path.suffix or '<none>'}' for {path.name}. "
            "Use an .mp4 source file."
        )
    if not path.stat().st_size:
        raise IngestValidationError(
            f"Input file is empty: {path}. " "Use a non-empty .mp4 file."
        )
    try:
        with path.open("rb"):
            pass
    except OSError as exc:
        raise IngestValidationError(
            f"Input file is not readable: {path} ({exc}). "
            "Check file permissions and retry."
        ) from exc

    return path.resolve()
