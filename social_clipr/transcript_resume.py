"""Validation helpers for resume-from-transcript pipeline mode."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from social_clipr.bundle import TRANSCRIPT_JSON_NAME, TRANSCRIPT_TXT_NAME
from social_clipr.word_cues import normalize_word_cues, serialize_word_cues


class TranscriptResumeError(ValueError):
    """Raised when transcript resume prerequisites fail."""


def expected_job_dir(input_path: Path, output_root: Path) -> Path:
    """Return ``output_root / <input_basename_without_suffix>`` (not required to exist)."""
    return output_root / input_path.stem


def expected_transcript_json(input_path: Path, output_root: Path) -> Path:
    """Return the canonical transcript.json path for a resume of ``input_path``."""
    return expected_job_dir(input_path, output_root) / TRANSCRIPT_JSON_NAME


def ensure_transcript_json_matches_input(
    transcript_json: Path, input_path: Path
) -> None:
    """Reject a transcript path whose parent folder stem does not match ``input_path``."""
    input_path = input_path.resolve()
    transcript_json = transcript_json.resolve()
    parent_stem = transcript_json.parent.name
    if parent_stem != input_path.stem:
        raise TranscriptResumeError(
            f"Transcript file {transcript_json} is under job folder '{parent_stem}', "
            f"but --input basename is '{input_path.stem}'. "
            "The outputs/<stem>/ folder must use the same stem as the .mp4 filename."
        )


def resolve_transcript_json_for_resume(
    input_path: Path,
    *,
    output_root: Path | None = None,
) -> Path:
    """Return ``output_root/<stem>/transcript.json`` if it exists and contains parseable JSON.

    ``input_path`` should already be validated (e.g. via :func:`social_clipr.ingest.validate_input_mp4`).
    """
    input_path = input_path.resolve()
    root = Path("outputs").resolve() if output_root is None else output_root.resolve()
    transcript_path = expected_transcript_json(input_path, root)

    if not transcript_path.is_file():
        raise TranscriptResumeError(
            f"Transcript resume requires {transcript_path}. "
            f"Run a full pipeline first or place transcript.json under outputs/{input_path.stem}/."
        )

    ensure_transcript_json_matches_input(transcript_path, input_path)

    try:
        text = transcript_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TranscriptResumeError(
            f"Cannot read transcript file {transcript_path}: {exc}"
        ) from exc

    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        raise TranscriptResumeError(
            f"Transcript file is not valid JSON: {transcript_path} ({exc})"
        ) from exc

    return transcript_path


def ensure_transcript_txt(transcript_json: Path) -> Path:
    """Return ``transcript.txt`` next to JSON, creating it from ``segments`` if missing."""
    transcript_json = transcript_json.resolve()
    txt_path = transcript_json.parent / TRANSCRIPT_TXT_NAME
    if txt_path.is_file():
        return txt_path

    payload = cast(
        dict[str, Any],
        json.loads(transcript_json.read_text(encoding="utf-8")),
    )
    raw_segments = payload.get("segments")
    lines: list[str] = []
    if isinstance(raw_segments, list):
        for row in raw_segments:
            if isinstance(row, dict):
                lines.append(str(row.get("text", "")).strip())
    txt_path.write_text(
        "\n".join(lines) + ("\n" if lines else ""),
        encoding="utf-8",
    )
    return txt_path


def apply_refresh_word_cues_to_file(transcript_json: Path) -> None:
    """Rebuild ``word_cues`` from ``segments`` only and rewrite ``transcript_json`` on disk."""
    transcript_json = transcript_json.resolve()
    payload = cast(
        dict[str, Any],
        json.loads(transcript_json.read_text(encoding="utf-8")),
    )
    raw_segments = payload.get("segments")
    segments: list[Any] = raw_segments if isinstance(raw_segments, list) else []
    synthetic: dict[str, object] = {"segments": segments}
    cues = normalize_word_cues(synthetic)
    payload["word_cues"] = serialize_word_cues(cues)
    payload["word_cue_count"] = len(cues)
    transcript_json.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
