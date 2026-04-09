"""Unit tests for caption file generation."""

from __future__ import annotations

import json
from pathlib import Path

from social_clipr.captions import write_caption_artifacts


def test_write_caption_artifacts_one_word_per_cue_from_word_cues(
    tmp_path: Path,
) -> None:
    transcript = tmp_path / "transcript.json"
    payload = {
        "source": str(tmp_path / "in.mp4"),
        "segment_count": 1,
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "one two"},
        ],
        "word_cues": [
            {"start": 0.0, "end": 0.3, "text": "one"},
            {"start": 0.3, "end": 1.0, "text": "two"},
        ],
    }
    transcript.write_text(json.dumps(payload), encoding="utf-8")

    out = write_caption_artifacts(transcript)
    srt_text = Path(out["srt"]).read_text(encoding="utf-8")
    vtt_text = Path(out["vtt"]).read_text(encoding="utf-8")

    assert srt_text == (
        "1\n"
        "00:00:00,000 --> 00:00:00,300\n"
        "one\n"
        "\n"
        "2\n"
        "00:00:00,300 --> 00:00:01,000\n"
        "two\n"
    )
    assert vtt_text == (
        "WEBVTT\n"
        "\n"
        "00:00:00.000 --> 00:00:00.300\n"
        "one\n"
        "\n"
        "00:00:00.300 --> 00:00:01.000\n"
        "two\n"
    )


def test_write_caption_artifacts_splits_segment_when_no_word_cues(
    tmp_path: Path,
) -> None:
    transcript = tmp_path / "transcript.json"
    payload = {
        "source": str(tmp_path / "in.mp4"),
        "segment_count": 1,
        "segments": [
            {"start": 0.0, "end": 2.0, "text": "hello world"},
        ],
    }
    transcript.write_text(json.dumps(payload), encoding="utf-8")

    out = write_caption_artifacts(transcript)
    srt_text = Path(out["srt"]).read_text(encoding="utf-8")
    lines = [ln for ln in srt_text.strip().split("\n") if ln]
    assert lines[0] == "1"
    assert "hello" in srt_text
    assert "2\n" in srt_text or srt_text.split("\n")[4] == "2"
    assert "world" in srt_text
    vtt_body = Path(out["vtt"]).read_text(encoding="utf-8")
    assert vtt_body.startswith("WEBVTT\n")
    assert "hello" in vtt_body and "world" in vtt_body


def test_write_caption_artifacts_legacy_two_single_word_segments(
    tmp_path: Path,
) -> None:
    transcript = tmp_path / "transcript.json"
    payload = {
        "source": str(tmp_path / "in.mp4"),
        "segment_count": 2,
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "hello"},
            {"start": 1.0, "end": 2.5, "text": "world"},
        ],
    }
    transcript.write_text(json.dumps(payload), encoding="utf-8")

    out = write_caption_artifacts(transcript)
    srt = Path(out["srt"])
    vtt = Path(out["vtt"])
    assert srt.read_text(encoding="utf-8").startswith("1\n")
    assert " --> " in srt.read_text(encoding="utf-8")
    vtt_body = vtt.read_text(encoding="utf-8")
    assert vtt_body.startswith("WEBVTT\n")
    assert "hello" in vtt_body and "world" in vtt_body


def test_write_caption_artifacts_ignore_stored_word_cues_uses_segments(
    tmp_path: Path,
) -> None:
    transcript = tmp_path / "transcript.json"
    payload = {
        "segments": [{"start": 0.0, "end": 2.0, "text": "alpha bravo"}],
        "word_cues": [
            {"start": 0.0, "end": 1.0, "text": "stale"},
        ],
    }
    transcript.write_text(json.dumps(payload), encoding="utf-8")

    out = write_caption_artifacts(transcript, ignore_stored_word_cues=True)
    srt = Path(out["srt"]).read_text(encoding="utf-8")
    assert "alpha" in srt and "bravo" in srt
    assert "stale" not in srt
