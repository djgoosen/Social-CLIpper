"""Deterministic job bundle layout under ``outputs/<input-stem>/``."""

from __future__ import annotations

from pathlib import Path

# Canonical filenames (single source of truth for package / smoke / docs).
TRANSCRIPT_JSON_NAME = "transcript.json"
TRANSCRIPT_TXT_NAME = "transcript.txt"
CAPTIONS_SRT_NAME = "captions.srt"
CAPTIONS_VTT_NAME = "captions.vtt"
RUN_SUMMARY_NAME = "run_summary.json"
METADATA_DRAFT_NAME = "metadata_draft.json"

BUNDLE_LAYOUT_VERSION = 1


def rendered_video_filename(encode_profile_id: str) -> str:
    """Final MP4 basename for encode profile ``encode_profile_id``."""
    return f"rendered-{encode_profile_id}.mp4"


def expected_bundle_relative_paths(encode_profile_id: str) -> tuple[str, ...]:
    """Ordered list of every file a complete MVP job directory should contain."""
    vid = rendered_video_filename(encode_profile_id)
    return (
        TRANSCRIPT_JSON_NAME,
        TRANSCRIPT_TXT_NAME,
        CAPTIONS_SRT_NAME,
        CAPTIONS_VTT_NAME,
        vid,
        RUN_SUMMARY_NAME,
        METADATA_DRAFT_NAME,
    )


def missing_bundle_files(job_dir: Path, encode_profile_id: str) -> list[str]:
    """Return relative paths that are not present as files (empty if bundle is complete)."""
    job_dir = job_dir.resolve()
    missing: list[str] = []
    for rel in expected_bundle_relative_paths(encode_profile_id):
        if not (job_dir / rel).is_file():
            missing.append(rel)
    return missing
