"""Tests for declarative config loading and validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from social_clipr.cli import main
from social_clipr.config_loader import ConfigError, load_pipeline_config


def _write_valid_tree(
    root: Path,
    *,
    stt_engine: str = "stub",
    stt_model: str = "",
    stt_language: str = "",
) -> None:
    enc = root / "encode"
    sty = root / "subtitle_styles"
    enc.mkdir(parents=True)
    sty.mkdir(parents=True)
    (enc / "shorts-vertical.json").write_text(
        json.dumps(
            {
                "id": "shorts-vertical",
                "width": 1080,
                "height": 1920,
                "frame_rate": 30,
                "video_filter": "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                "video_codec": "libx264",
                "crf": 23,
                "encoder_preset": "fast",
                "audio_codec": "aac",
                "audio_bitrate_kbps": 128,
            }
        ),
        encoding="utf-8",
    )
    (sty / "minimal.json").write_text(
        json.dumps(
            {
                "id": "minimal",
                "font_family": "Arial",
                "font_size": 42,
                "primary_color": "&HFFFFFF&",
                "outline_color": "&H000000&",
                "outline_width": 2,
                "margin_v": 120,
                "alignment": 2,
            }
        ),
        encoding="utf-8",
    )
    (sty / "bold_social.json").write_text(
        json.dumps(
            {
                "id": "bold_social",
                "font_family": "Arial Black",
                "font_size": 52,
                "primary_color": "&H00FFFF&",
                "outline_color": "&H000000&",
                "outline_width": 4,
                "margin_v": 100,
                "alignment": 2,
            }
        ),
        encoding="utf-8",
    )
    (root / "stt.json").write_text(
        json.dumps(
            {
                "engine": stt_engine,
                "model": stt_model,
                "language": stt_language,
            }
        ),
        encoding="utf-8",
    )


def test_load_bundled_configs_ok() -> None:
    cfg = load_pipeline_config(None)
    assert "shorts-vertical" in cfg.encode_profiles
    assert cfg.encode_profiles["shorts-vertical"].width == 1080
    assert "minimal" in cfg.subtitle_styles
    assert "bold_social" in cfg.subtitle_styles
    assert "purple_lower_third" in cfg.subtitle_styles
    assert cfg.stt.engine == "whisper_cli"
    assert cfg.stt.model == "tiny"


def test_bundled_shorts_vertical_fit_letterboxes_with_pad() -> None:
    """Letterbox profile scales down to fit then pads to 1080×1920 (no center-crop chain)."""
    cfg = load_pipeline_config(None)
    assert "shorts-vertical-fit" in cfg.encode_profiles
    fit = cfg.encode_profiles["shorts-vertical-fit"]
    assert fit.width == 1080
    assert fit.height == 1920
    vf = fit.video_filter
    assert "force_original_aspect_ratio=decrease" in vf
    assert "pad=1080:1920" in vf
    assert "crop=" not in vf
    crop_prof = cfg.encode_profiles["shorts-vertical"]
    assert "crop=1080:1920" in crop_prof.video_filter
    assert "force_original_aspect_ratio=increase" in crop_prof.video_filter


def test_bundled_purple_lower_third_style() -> None:
    cfg = load_pipeline_config(None)
    p = cfg.subtitle_styles["purple_lower_third"]
    assert p.alignment == 2
    assert p.margin_v == 160
    assert p.primary_color == "&HD355BA&"


def test_bundled_subtitle_styles_lower_center_defaults() -> None:
    """Shipped presets use ASS alignment 2 (bottom-center) and vertical margin for lower-third."""
    cfg = load_pipeline_config(None)
    minimal = cfg.subtitle_styles["minimal"]
    bold = cfg.subtitle_styles["bold_social"]
    assert minimal.alignment == 2 and bold.alignment == 2
    assert minimal.margin_v == 160
    assert bold.margin_v == 152


def test_bundled_youtube_horizontal_landscape_profile() -> None:
    """1920×1080 letterbox profile for laptop / YouTube-style exports (PRD horizontal spec)."""
    cfg = load_pipeline_config(None)
    assert "youtube-horizontal" in cfg.encode_profiles
    h = cfg.encode_profiles["youtube-horizontal"]
    assert h.width == 1920
    assert h.height == 1080
    assert "pad=1920:1080" in h.video_filter
    assert "force_original_aspect_ratio=decrease" in h.video_filter
    assert "shorts-vertical" in cfg.encode_profiles
    assert "shorts-vertical-fit" in cfg.encode_profiles


def test_invalid_json_rejected(tmp_path: Path) -> None:
    root = tmp_path / "configs"
    _write_valid_tree(root)
    (root / "encode" / "broken.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid JSON"):
        load_pipeline_config(root)


def test_id_must_match_file_stem(tmp_path: Path) -> None:
    root = tmp_path / "configs"
    _write_valid_tree(root)
    (root / "encode" / "shorts-vertical.json").write_text(
        json.dumps(
            {
                "id": "wrong-id",
                "width": 1080,
                "height": 1920,
                "frame_rate": 30,
                "video_filter": (
                    "scale=1080:1920:force_original_aspect_ratio=increase,"
                    "crop=1080:1920"
                ),
                "video_codec": "libx264",
                "crf": 23,
                "encoder_preset": "fast",
                "audio_codec": "aac",
                "audio_bitrate_kbps": 128,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="must match file name stem"):
        load_pipeline_config(root)


def test_requires_two_subtitle_styles(tmp_path: Path) -> None:
    root = tmp_path / "configs"
    enc = root / "encode"
    sty = root / "subtitle_styles"
    enc.mkdir(parents=True)
    sty.mkdir(parents=True)
    (enc / "shorts-vertical.json").write_text(
        json.dumps(
            {
                "id": "shorts-vertical",
                "width": 1080,
                "height": 1920,
                "frame_rate": 30,
                "video_filter": (
                    "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
                ),
                "video_codec": "libx264",
                "crf": 23,
                "encoder_preset": "fast",
                "audio_codec": "aac",
                "audio_bitrate_kbps": 128,
            }
        ),
        encoding="utf-8",
    )
    (sty / "only_one.json").write_text(
        json.dumps(
            {
                "id": "only_one",
                "font_family": "Arial",
                "font_size": 42,
                "primary_color": "&HFFFFFF&",
                "outline_color": "&H000000&",
                "outline_width": 2,
                "margin_v": 120,
                "alignment": 2,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="At least two subtitle style"):
        load_pipeline_config(root)


def test_cli_config_error_returns_two(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    bad = tmp_path / "not-a-dir"
    bad.mkdir()
    (bad / "file.txt").write_text("x", encoding="utf-8")
    result = main(
        [
            "run",
            "--input",
            "x.mp4",
            "--profile",
            "shorts-vertical",
            "--config-dir",
            str(bad / "missing"),
        ]
    )
    out = capsys.readouterr().out
    assert result == 2
    assert "Config error" in out


def test_crf_out_of_range_rejected(tmp_path: Path) -> None:
    root = tmp_path / "configs"
    _write_valid_tree(root)
    data = json.loads(
        (root / "encode" / "shorts-vertical.json").read_text(encoding="utf-8")
    )
    data["crf"] = 99
    (root / "encode" / "shorts-vertical.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="crf must be between"):
        load_pipeline_config(root)


def test_missing_stt_json_rejected(tmp_path: Path) -> None:
    root = tmp_path / "configs"
    _write_valid_tree(root)
    (root / "stt.json").unlink()
    with pytest.raises(ConfigError, match="Missing speech-to-text config"):
        load_pipeline_config(root)


def test_stt_invalid_engine_rejected(tmp_path: Path) -> None:
    root = tmp_path / "configs"
    _write_valid_tree(root, stt_engine="cloud_api")
    with pytest.raises(ConfigError, match="engine must be one of"):
        load_pipeline_config(root)


def test_stt_whisper_requires_model(tmp_path: Path) -> None:
    root = tmp_path / "configs"
    _write_valid_tree(root, stt_engine="whisper_cli", stt_model="")
    with pytest.raises(ConfigError, match="model must be non-empty"):
        load_pipeline_config(root)


def test_encode_video_filter_rejects_mismatched_output_dimensions(
    tmp_path: Path,
) -> None:
    root = tmp_path / "configs"
    _write_valid_tree(root)
    bad = {
        "id": "shorts-vertical",
        "width": 1080,
        "height": 1920,
        "frame_rate": 30,
        "video_filter": "scale=1080:1920:force_original_aspect_ratio=increase,crop=720:1280",
        "video_codec": "libx264",
        "crf": 23,
        "encoder_preset": "fast",
        "audio_codec": "aac",
        "audio_bitrate_kbps": 128,
    }
    (root / "encode" / "shorts-vertical.json").write_text(
        json.dumps(bad), encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="video_filter must contain at least one of"):
        load_pipeline_config(root)


def test_encode_video_filter_accepts_pad_matching_dimensions(tmp_path: Path) -> None:
    root = tmp_path / "configs"
    _write_valid_tree(root)
    pad_vf = (
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
    )
    data = json.loads(
        (root / "encode" / "shorts-vertical.json").read_text(encoding="utf-8")
    )
    data["video_filter"] = pad_vf
    (root / "encode" / "shorts-vertical.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    cfg = load_pipeline_config(root)
    assert cfg.encode_profiles["shorts-vertical"].video_filter == pad_vf


def test_encode_video_filter_accepts_scale_only_matching_dimensions(
    tmp_path: Path,
) -> None:
    root = tmp_path / "configs"
    _write_valid_tree(root)
    (root / "encode" / "landscape.json").write_text(
        json.dumps(
            {
                "id": "landscape",
                "width": 1920,
                "height": 1080,
                "frame_rate": 30,
                "video_filter": "scale=1920:1080",
                "video_codec": "libx264",
                "crf": 23,
                "encoder_preset": "fast",
                "audio_codec": "aac",
                "audio_bitrate_kbps": 128,
            }
        ),
        encoding="utf-8",
    )
    cfg = load_pipeline_config(root)
    assert "landscape" in cfg.encode_profiles
    assert cfg.encode_profiles["landscape"].video_filter == "scale=1920:1080"


def test_encode_video_filter_rejects_pad_with_wrong_dimensions(tmp_path: Path) -> None:
    root = tmp_path / "configs"
    _write_valid_tree(root)
    bad_vf = (
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=720:1280:(ow-iw)/2:(oh-ih)/2"
    )
    data = json.loads(
        (root / "encode" / "shorts-vertical.json").read_text(encoding="utf-8")
    )
    data["video_filter"] = bad_vf
    (root / "encode" / "shorts-vertical.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="video_filter must contain at least one of"):
        load_pipeline_config(root)
