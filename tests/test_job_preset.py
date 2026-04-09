"""Tests for job preset JSON load/save (FR7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from social_clipr.job_preset import (
    JOB_PRESET_VERSION,
    JobPresetError,
    load_job_preset,
    save_job_preset,
)
from social_clipr.pipeline import subtitle_font_size_from_environment


def test_roundtrip_minimal(tmp_path: Path) -> None:
    p = tmp_path / "job.json"
    save_job_preset(
        p,
        profile="shorts-vertical",
        subtitle_style="minimal",
    )
    data = load_job_preset(p)
    assert data["profile"] == "shorts-vertical"
    assert data["subtitle_style"] == "minimal"
    assert data["config_dir"] is None
    assert data["subtitle_font_size"] is None
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["version"] == JOB_PRESET_VERSION


def test_save_with_config_dir(tmp_path: Path) -> None:
    cfg_root = tmp_path / "configs"
    (cfg_root / "encode").mkdir(parents=True)
    (cfg_root / "subtitle_styles").mkdir(parents=True)
    p = tmp_path / "job.json"
    save_job_preset(
        p,
        profile="shorts-vertical",
        subtitle_style="bold_social",
        config_dir=cfg_root,
    )
    data = load_job_preset(p)
    assert data["config_dir"] == cfg_root.resolve()


def test_save_rejects_bad_profile(tmp_path: Path) -> None:
    with pytest.raises(JobPresetError, match="profile"):
        save_job_preset(
            tmp_path / "nope.json",
            profile="bad;rm",
            subtitle_style="minimal",
        )


def test_load_rejects_shell_chars_in_profile(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text(
        json.dumps(
            {
                "version": JOB_PRESET_VERSION,
                "profile": "x;y",
                "subtitle_style": "minimal",
                "config_dir": None,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(JobPresetError, match="disallowed"):
        load_job_preset(p)


def test_load_rejects_wrong_version(tmp_path: Path) -> None:
    p = tmp_path / "v.json"
    p.write_text(
        '{"version": 99, "profile": "shorts-vertical", "subtitle_style": "minimal", "config_dir": null}',
        encoding="utf-8",
    )
    with pytest.raises(JobPresetError, match="Unsupported preset version"):
        load_job_preset(p)


def test_roundtrip_subtitle_font_size(tmp_path: Path) -> None:
    p = tmp_path / "job.json"
    save_job_preset(
        p,
        profile="shorts-vertical",
        subtitle_style="minimal",
        subtitle_font_size=120,
    )
    data = load_job_preset(p)
    assert data["subtitle_font_size"] == 120
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["subtitle_font_size"] == 120


def test_load_rejects_subtitle_font_size_out_of_range(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text(
        json.dumps(
            {
                "version": JOB_PRESET_VERSION,
                "profile": "shorts-vertical",
                "subtitle_style": "minimal",
                "config_dir": None,
                "subtitle_font_size": 3,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(JobPresetError, match="at least"):
        load_job_preset(p)


def test_load_accepts_preset_without_subtitle_font_size_key(tmp_path: Path) -> None:
    """Older presets without the key still load."""
    p = tmp_path / "legacy.json"
    p.write_text(
        json.dumps(
            {
                "version": JOB_PRESET_VERSION,
                "profile": "shorts-vertical",
                "subtitle_style": "minimal",
                "config_dir": None,
            }
        ),
        encoding="utf-8",
    )
    data = load_job_preset(p)
    assert data["subtitle_font_size"] is None


def test_save_config_dir_must_exist(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    with pytest.raises(JobPresetError, match="not a directory"):
        save_job_preset(
            tmp_path / "out.json",
            profile="shorts-vertical",
            subtitle_style="minimal",
            config_dir=missing,
        )


def test_subtitle_font_size_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SOCIAL_CLIPR_SUBTITLE_FONT_SIZE", raising=False)
    assert subtitle_font_size_from_environment() is None
    monkeypatch.setenv("SOCIAL_CLIPR_SUBTITLE_FONT_SIZE", " 40 ")
    assert subtitle_font_size_from_environment() == 40
    monkeypatch.setenv("SOCIAL_CLIPR_SUBTITLE_FONT_SIZE", "x")
    with pytest.raises(ValueError, match="integer"):
        subtitle_font_size_from_environment()
