"""Smoke script and optional real-media / STT edge paths."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from social_clipr.config_loader import load_pipeline_config
from social_clipr.render import _ffmpeg_has_subtitles_filter
from social_clipr.transcribe import write_transcript_artifacts
from tests.test_config_loader import _write_valid_tree


def test_faster_whisper_missing_package_falls_back_to_stub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CI stays light: no faster-whisper install; engine still resolves to stub."""
    import builtins

    real_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object):
        if name == "faster_whisper":
            raise ImportError("simulated missing faster_whisper")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    root = tmp_path / "configs"
    _write_valid_tree(root, stt_engine="faster_whisper", stt_model="tiny")
    cfg = load_pipeline_config(root)
    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"y")
    monkeypatch.delenv("SOCIAL_CLIPR_TRANSCRIBE", raising=False)
    out = write_transcript_artifacts(inp, cfg, output_root=tmp_path / "outputs")
    payload = json.loads(out["json"].read_text(encoding="utf-8"))
    assert payload["engine"] == "stub"


def test_smoke_script_quick_mode_succeeds() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHON": sys.executable}
    env.pop("SOCIAL_CLIPR_SMOKE_REAL", None)
    r = subprocess.run(
        ["bash", str(repo / "scripts" / "smoke_run.sh")],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg on PATH")
@pytest.mark.skipif(
    not _ffmpeg_has_subtitles_filter(shutil.which("ffmpeg") or ""),
    reason="real smoke needs ffmpeg with libass subtitles filter",
)
def test_smoke_script_real_mode_bundle_flags() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHON": sys.executable, "SOCIAL_CLIPR_SMOKE_REAL": "1"}
    for k in (
        "SOCIAL_CLIPR_RENDER",
        "SOCIAL_CLIPR_TRANSCRIBE",
        "SOCIAL_CLIPR_SMOKE_WHISPER",
    ):
        env.pop(k, None)
    r = subprocess.run(
        ["bash", str(repo / "scripts" / "smoke_run.sh")],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert (
        "SOCIAL_CLIPR_SMOKE_REAL=1" in r.stdout
        or "[SOCIAL_CLIPR_SMOKE_REAL=1]" in r.stdout
    )


@pytest.mark.skipif(
    not shutil.which("ffmpeg"), reason="script checks ffmpeg before whisper"
)
@pytest.mark.skipif(
    shutil.which("whisper") is not None,
    reason="only meaningful when whisper CLI is absent",
)
def test_smoke_whisper_strict_exits_when_whisper_missing() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = {
        **os.environ,
        "PYTHON": sys.executable,
        "SOCIAL_CLIPR_SMOKE_REAL": "1",
        "SOCIAL_CLIPR_SMOKE_WHISPER": "1",
    }
    for k in ("SOCIAL_CLIPR_RENDER", "SOCIAL_CLIPR_TRANSCRIBE"):
        env.pop(k, None)
    r = subprocess.run(
        ["bash", str(repo / "scripts" / "smoke_run.sh")],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode != 0
    assert "whisper" in r.stderr.lower()
