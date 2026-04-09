"""Tests for config-driven transcription."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from social_clipr.config_loader import load_pipeline_config
from social_clipr.transcribe import (
    _path_looks_like_pyenv_shim,
    write_transcript_artifacts,
)
from tests.test_config_loader import _write_valid_tree


def test_whisper_cli_uses_stt_config_and_writes_segments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "configs"
    _write_valid_tree(root, stt_engine="whisper_cli", stt_model="base", stt_language="")
    cfg = load_pipeline_config(root)

    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"fake")

    def fake_which(cmd: str) -> str | None:
        return "/fake/whisper" if cmd == "whisper" else None

    def fake_run(
        cmd: list[str],
        *,
        capture_output: bool = True,
        text: bool = True,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        out_dir = cmd[cmd.index("--output_dir") + 1]
        stem = Path(cmd[cmd.index("--output_dir") - 1]).stem
        assert "--model" in cmd
        mi = cmd.index("--model")
        assert cmd[mi + 1] == "base"
        whisper_json = Path(out_dir) / f"{stem}.json"
        whisper_json.write_text(
            json.dumps(
                {
                    "segments": [
                        {"start": 0.0, "end": 0.5, "text": "hello from mock"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("social_clipr.transcribe.shutil.which", fake_which)
    monkeypatch.setattr("social_clipr.transcribe.subprocess.run", fake_run)
    monkeypatch.delenv("SOCIAL_CLIPR_TRANSCRIBE", raising=False)
    monkeypatch.delenv("SOCIAL_CLIPR_WHISPER_MODEL", raising=False)

    out = write_transcript_artifacts(inp, cfg, output_root=tmp_path / "outputs")
    payload = json.loads(out["json"].read_text(encoding="utf-8"))
    assert payload["engine"] == "whisper_cli:base"
    assert len(payload["segments"]) == 1
    assert payload["segments"][0]["text"] == "hello from mock"
    assert payload["word_cue_count"] == 3
    assert [cue["text"] for cue in payload["word_cues"]] == ["hello", "from", "mock"]


def test_whisper_cli_uses_native_word_timings_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "configs"
    _write_valid_tree(root, stt_engine="whisper_cli", stt_model="base", stt_language="")
    cfg = load_pipeline_config(root)
    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"fake")

    monkeypatch.setattr("social_clipr.transcribe.shutil.which", lambda _: "/w")
    monkeypatch.delenv("SOCIAL_CLIPR_TRANSCRIBE", raising=False)
    monkeypatch.delenv("SOCIAL_CLIPR_WHISPER_MODEL", raising=False)

    def fake_run(
        cmd: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        out_dir = cmd[cmd.index("--output_dir") + 1]
        stem = Path(cmd[cmd.index("--output_dir") - 1]).stem
        Path(out_dir).joinpath(f"{stem}.json").write_text(
            json.dumps(
                {
                    "segments": [
                        {
                            "start": 0.0,
                            "end": 1.0,
                            "text": "hello world",
                            "words": [
                                {"word": "hello", "start": 0.0, "end": 0.35},
                                {"word": "world", "start": 0.35, "end": 1.0},
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("social_clipr.transcribe.subprocess.run", fake_run)
    out = write_transcript_artifacts(inp, cfg, output_root=tmp_path / "out")
    payload = json.loads(out["json"].read_text(encoding="utf-8"))
    seg0 = payload["segments"][0]
    assert "words" in seg0
    assert seg0["words"][0]["text"] == "hello"
    cues = payload["word_cues"]
    assert len(cues) == 2
    assert cues[0] == {"start": 0.0, "end": 0.35, "text": "hello"}
    assert cues[1] == {"start": 0.35, "end": 1.0, "text": "world"}


def test_env_overrides_whisper_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "configs"
    _write_valid_tree(root, stt_engine="whisper_cli", stt_model="tiny", stt_language="")
    cfg = load_pipeline_config(root)
    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"fake")
    monkeypatch.setenv("SOCIAL_CLIPR_WHISPER_MODEL", "small")
    captured: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        captured.append(cmd)
        out_dir = cmd[cmd.index("--output_dir") + 1]
        stem = Path(cmd[cmd.index("--output_dir") - 1]).stem
        Path(out_dir).joinpath(f"{stem}.json").write_text(
            json.dumps({"segments": [{"start": 0, "end": 1, "text": "x"}]}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("social_clipr.transcribe.shutil.which", lambda _: "/w")
    monkeypatch.setattr("social_clipr.transcribe.subprocess.run", fake_run)
    monkeypatch.delenv("SOCIAL_CLIPR_TRANSCRIBE", raising=False)

    write_transcript_artifacts(inp, cfg, output_root=tmp_path / "o")
    assert captured and captured[0][captured[0].index("--model") + 1] == "small"


def test_stub_engine_skips_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "configs"
    _write_valid_tree(root)
    cfg = load_pipeline_config(root)
    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"fake")
    mock_run = MagicMock()
    monkeypatch.setattr("social_clipr.transcribe.subprocess.run", mock_run)
    monkeypatch.delenv("SOCIAL_CLIPR_TRANSCRIBE", raising=False)

    write_transcript_artifacts(inp, cfg, output_root=tmp_path / "o")
    mock_run.assert_not_called()
    payload = json.loads(
        (tmp_path / "o" / "clip" / "transcript.json").read_text(encoding="utf-8")
    )
    assert payload["engine"] == "stub"
    assert payload["word_cue_count"] > 0
    assert isinstance(payload["word_cues"], list)


def test_path_looks_like_pyenv_shim(tmp_path: Path) -> None:
    shim = tmp_path / ".pyenv" / "shims" / "whisper"
    shim.parent.mkdir(parents=True)
    shim.write_text("#", encoding="utf-8")
    assert _path_looks_like_pyenv_shim(str(shim)) is True
    other = tmp_path / "bin" / "whisper"
    other.parent.mkdir(parents=True)
    other.write_text("#", encoding="utf-8")
    assert _path_looks_like_pyenv_shim(str(other)) is False


def test_whisper_cli_skips_pyenv_shim_when_package_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util

    shim = tmp_path / ".pyenv" / "shims" / "whisper"
    shim.parent.mkdir(parents=True)
    shim.write_text("#!/bin/sh\necho\n", encoding="utf-8")

    _real_find_spec = importlib.util.find_spec

    def find_spec_no_whisper(name: str, package: str | None = None) -> object | None:
        if name == "whisper":
            return None
        return _real_find_spec(name, package)

    monkeypatch.setattr(
        "social_clipr.transcribe.importlib.util.find_spec", find_spec_no_whisper
    )
    monkeypatch.setattr("social_clipr.transcribe.shutil.which", lambda _: str(shim))
    mock_run = MagicMock()
    monkeypatch.setattr("social_clipr.transcribe.subprocess.run", mock_run)
    monkeypatch.delenv("SOCIAL_CLIPR_TRANSCRIBE", raising=False)
    monkeypatch.delenv("SOCIAL_CLIPR_WHISPER_MODEL", raising=False)

    root = tmp_path / "configs"
    _write_valid_tree(root, stt_engine="whisper_cli", stt_model="tiny", stt_language="")
    cfg = load_pipeline_config(root)
    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"fake")

    write_transcript_artifacts(inp, cfg, output_root=tmp_path / "out")
    mock_run.assert_not_called()
    payload = json.loads(
        (tmp_path / "out" / "clip" / "transcript.json").read_text(encoding="utf-8")
    )
    assert payload["engine"] == "stub"
