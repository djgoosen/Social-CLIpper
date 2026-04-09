"""Tests for job bundle layout and run summary manifest."""

from __future__ import annotations

import json
from pathlib import Path

from social_clipr.bundle import (
    expected_bundle_relative_paths,
    missing_bundle_files,
    rendered_video_filename,
)
from social_clipr.cli import main


def test_expected_bundle_paths_match_render_naming() -> None:
    paths = expected_bundle_relative_paths("shorts-vertical")
    assert paths[-3] == rendered_video_filename("shorts-vertical")


def test_stub_run_produces_complete_bundle(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SOCIAL_CLIPR_RENDER", "stub")
    monkeypatch.setenv("SOCIAL_CLIPR_TRANSCRIBE", "stub")
    monkeypatch.chdir(tmp_path)
    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"x")
    assert main(["run", "--input", str(inp), "--profile", "shorts-vertical"]) == 0
    job = tmp_path / "outputs" / "clip"
    missing = missing_bundle_files(job, "shorts-vertical")
    assert missing == []
    summary = json.loads((job / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["bundle"]["layout_version"] == 1
    assert summary["bundle"]["render_mode"] == "stub_copy"
    assert summary["bundle"]["video_includes_burned_subtitles"] is False
    assert summary["bundle"]["expected_files"] == list(
        expected_bundle_relative_paths("shorts-vertical")
    )
    meta = json.loads((job / "metadata_draft.json").read_text(encoding="utf-8"))
    assert meta["encode_profile"] == "shorts-vertical"
    assert meta["subtitle_style"] == "minimal"
    assert meta["source_media"] == "clip.mp4"
    assert meta["export"]["final_video"] == "rendered-shorts-vertical.mp4"
    assert summary["subtitle_font_size"] == 36
    assert meta["subtitle_font_size"] == 36
    assert "job_preset" not in summary
    assert "job_preset" not in meta


def test_stub_run_records_subtitle_font_size_override(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SOCIAL_CLIPR_RENDER", "stub")
    monkeypatch.setenv("SOCIAL_CLIPR_TRANSCRIBE", "stub")
    monkeypatch.chdir(tmp_path)
    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"x")
    assert (
        main(
            [
                "run",
                "--input",
                str(inp),
                "--profile",
                "shorts-vertical",
                "--subtitle-font-size",
                "72",
            ]
        )
        == 0
    )
    job = tmp_path / "outputs" / "clip"
    summary = json.loads((job / "run_summary.json").read_text(encoding="utf-8"))
    meta = json.loads((job / "metadata_draft.json").read_text(encoding="utf-8"))
    assert summary["subtitle_font_size"] == 72
    assert meta["subtitle_font_size"] == 72
