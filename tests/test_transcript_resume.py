"""Tests for transcript resume path validation (PIN-033)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from social_clipr.transcript_resume import (
    TranscriptResumeError,
    apply_refresh_word_cues_to_file,
    ensure_transcript_json_matches_input,
    ensure_transcript_txt,
    expected_job_dir,
    expected_transcript_json,
    resolve_transcript_json_for_resume,
)


def test_expected_paths(tmp_path: Path) -> None:
    inp = tmp_path / "my_clip.mp4"
    root = tmp_path / "outputs"
    assert expected_job_dir(inp, root) == root / "my_clip"
    assert expected_transcript_json(inp, root) == root / "my_clip" / "transcript.json"


def test_resolve_happy(tmp_path: Path) -> None:
    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"x")
    root = tmp_path / "outputs"
    job = root / "clip"
    job.mkdir(parents=True)
    transcript = job / "transcript.json"
    transcript.write_text('{"segments": []}', encoding="utf-8")

    resolved = resolve_transcript_json_for_resume(inp, output_root=root)
    assert resolved.resolve() == transcript.resolve()


def test_resolve_missing_file(tmp_path: Path) -> None:
    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"x")
    root = tmp_path / "outputs"
    (root / "clip").mkdir(parents=True)

    with pytest.raises(TranscriptResumeError, match="Transcript resume requires"):
        resolve_transcript_json_for_resume(inp, output_root=root)


def test_resolve_bad_json(tmp_path: Path) -> None:
    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"x")
    root = tmp_path / "outputs"
    job = root / "clip"
    job.mkdir(parents=True)
    (job / "transcript.json").write_text("not json {", encoding="utf-8")

    with pytest.raises(TranscriptResumeError, match="not valid JSON"):
        resolve_transcript_json_for_resume(inp, output_root=root)


def test_ensure_mismatch_stem_rejected(tmp_path: Path) -> None:
    inp = tmp_path / "foo.mp4"
    inp.write_bytes(b"x")
    root = tmp_path / "outputs"
    other = root / "bar" / "transcript.json"
    other.parent.mkdir(parents=True)
    other.write_text("{}", encoding="utf-8")

    with pytest.raises(TranscriptResumeError, match="job folder 'bar'"):
        ensure_transcript_json_matches_input(other, inp)


def test_resolve_rejects_symlinked_job_dir_with_wrong_stem(tmp_path: Path) -> None:
    """If outputs/<input_stem> points at another folder name, resume must fail."""
    inp = tmp_path / "foo.mp4"
    inp.write_bytes(b"x")
    root = tmp_path / "outputs"
    real_job = root / "bar"
    real_job.mkdir(parents=True)
    (real_job / "transcript.json").write_text("{}", encoding="utf-8")
    link = root / "foo"
    try:
        link.symlink_to(real_job, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not supported in this environment")

    with pytest.raises(TranscriptResumeError, match="job folder 'bar'"):
        resolve_transcript_json_for_resume(inp, output_root=root)


def test_ensure_transcript_txt_creates_from_segments(tmp_path: Path) -> None:
    job = tmp_path / "out" / "c"
    job.mkdir(parents=True)
    tj = job / "transcript.json"
    tj.write_text(
        '{"segments": [{"start": 0, "end": 1, "text": "a b"}]}',
        encoding="utf-8",
    )
    txt = ensure_transcript_txt(tj)
    assert txt.read_text(encoding="utf-8").strip() == "a b"


def test_apply_refresh_word_cues_rewrites_from_segments(tmp_path: Path) -> None:
    job = tmp_path / "j"
    job.mkdir()
    tj = job / "transcript.json"
    tj.write_text(
        json.dumps(
            {
                "segments": [{"start": 0.0, "end": 2.0, "text": "hello there"}],
                "word_cues": [
                    {"start": 0.0, "end": 1.0, "text": "stale"},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    apply_refresh_word_cues_to_file(tj)
    data = json.loads(tj.read_text(encoding="utf-8"))
    assert len(data["word_cues"]) >= 2
    texts = [c["text"] for c in data["word_cues"]]
    assert "hello" in texts and "there" in texts
