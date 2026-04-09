"""Unit tests for ingest validation."""

from __future__ import annotations

import pytest
from social_clipr.ingest import IngestValidationError, validate_input_mp4


def test_validate_rejects_missing_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    missing = tmp_path / "nope.mp4"
    with pytest.raises(IngestValidationError, match="not found"):
        validate_input_mp4(str(missing))


def test_validate_rejects_non_mp4_extension(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "clip.mov"
    p.write_bytes(b"x")
    with pytest.raises(IngestValidationError, match="extension"):
        validate_input_mp4(str(p))


def test_validate_rejects_empty_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "empty.mp4"
    p.write_bytes(b"")
    with pytest.raises(IngestValidationError, match="empty"):
        validate_input_mp4(str(p))


def test_validate_accepts_readable_non_empty_mp4(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "ok.mp4"
    p.write_bytes(b"not-a-real-mp4-but-valid-for-ingest")
    resolved = validate_input_mp4(str(p))
    assert resolved == p.resolve()
