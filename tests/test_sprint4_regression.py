"""Sprint 4 regression: word-level cues, segment fallback timing, bundled subtitle placement."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from social_clipr.captions import write_caption_artifacts
from social_clipr.cli import main
from social_clipr.config_loader import load_pipeline_config
from social_clipr.render import build_video_filter
from social_clipr.transcribe import write_transcript_artifacts

REPO_ROOT = Path(__file__).resolve().parents[1]


def _srt_cue_count(srt_text: str) -> int:
    blocks = [b for b in srt_text.strip().split("\n\n") if b.strip()]
    return len(blocks)


def test_stub_transcript_word_cue_count_matches_caption_srt_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Transcribe (stub) → word_cues in JSON → captions must emit one SRT block per cue."""
    monkeypatch.setenv("SOCIAL_CLIPR_TRANSCRIBE", "stub")
    monkeypatch.delenv("SOCIAL_CLIPR_WHISPER_MODEL", raising=False)
    cfg = load_pipeline_config(REPO_ROOT / "configs")
    inp = tmp_path / "regress.mp4"
    inp.write_bytes(b"x")
    tdir = write_transcript_artifacts(inp, cfg, output_root=tmp_path / "outputs")
    payload = json.loads(tdir["json"].read_text(encoding="utf-8"))
    assert payload["engine"] == "stub"
    n_cues = int(payload["word_cue_count"])
    assert n_cues >= 4
    assert len(payload["word_cues"]) == n_cues
    caps = write_caption_artifacts(tdir["json"])
    srt_n = _srt_cue_count(caps["srt"].read_text(encoding="utf-8"))
    assert srt_n == n_cues


def test_transcript_segments_only_fallback_yields_word_level_captions(
    tmp_path: Path,
) -> None:
    """No word_cues / no per-segment words — split segment text; captions follow word order."""
    transcript = tmp_path / "transcript.json"
    transcript.write_text(
        json.dumps(
            {
                "segments": [
                    {"start": 0.0, "end": 1.0, "text": "alfa bravo"},
                    {"start": 1.0, "end": 3.0, "text": "charlie delta echo"},
                ]
            }
        ),
        encoding="utf-8",
    )
    out = write_caption_artifacts(transcript)
    body = out["srt"].read_text(encoding="utf-8")
    assert _srt_cue_count(body) == 5
    lines = body.strip().split("\n")
    assert lines[2] == "alfa"
    assert lines[-1] == "echo"


def test_run_stub_pipeline_captions_are_word_level_not_segment_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI run (stub ×2) writes SRT with one cue per word (more cues than stub segments)."""
    monkeypatch.setenv("SOCIAL_CLIPR_RENDER", "stub")
    monkeypatch.setenv("SOCIAL_CLIPR_TRANSCRIBE", "stub")
    monkeypatch.chdir(tmp_path)
    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"fake-mp4")
    assert (
        main(
            [
                "run",
                "--input",
                str(inp),
                "--profile",
                "shorts-vertical",
                "--subtitle-style",
                "minimal",
                "--config-dir",
                str(REPO_ROOT / "configs"),
            ]
        )
        == 0
    )
    job = tmp_path / "outputs" / "clip"
    payload = json.loads((job / "transcript.json").read_text(encoding="utf-8"))
    seg_n = len(payload["segments"])
    cue_n = int(payload["word_cue_count"])
    assert cue_n > seg_n
    srt_n = _srt_cue_count((job / "captions.srt").read_text(encoding="utf-8"))
    assert srt_n == cue_n


def test_bundled_subtitle_presets_keep_lower_center_in_render_path(
    tmp_path: Path,
) -> None:
    """Lock Sprint 4 margin_v + alignment in the burn-in video filter (with bundled configs)."""
    cfg = load_pipeline_config(REPO_ROOT / "configs")
    prof = cfg.encode_profiles["shorts-vertical"]
    srt = tmp_path / "c.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n", encoding="utf-8")
    for sid, margin in (("minimal", 24), ("bold_social", 23)):
        vf = build_video_filter(
            prof,
            subtitle_style=cfg.subtitle_styles[sid],
            captions_srt=srt,
        )
        assert r"Alignment=2" in vf
        assert rf"MarginV={margin}" in vf
        assert f":original_size={prof.width}x{prof.height}" in vf
