"""Tests for FFmpeg render driven by encode profile."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from social_clipr.config_loader import EncodeProfile, load_pipeline_config
from social_clipr.render import (
    RenderError,
    _ffmpeg_has_subtitles_filter,
    _ffmpeg_path,
    _force_style_arg,
    _force_style_token_for_subtitles_filter,
    _normalize_ass_colour,
    build_burnin_video_filter,
    build_ffmpeg_command,
    build_video_filter,
    write_render_artifact,
)


def _sample_profile() -> EncodeProfile:
    return EncodeProfile(
        id="test-vertical",
        width=720,
        height=1280,
        frame_rate=30,
        video_filter=(
            "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280"
        ),
        video_codec="libx264",
        crf=28,
        encoder_preset="veryfast",
        audio_codec="aac",
        audio_bitrate_kbps=96,
    )


def test_normalize_ass_colour_expands_six_digit_hex() -> None:
    assert _normalize_ass_colour("&HFFFFFF&") == "&H00FFFFFF&"


def test_force_style_token_escapes_commas_for_filtergraph() -> None:
    cfg = load_pipeline_config(None)
    tok = _force_style_token_for_subtitles_filter(cfg.subtitle_styles["minimal"])
    assert tok.startswith("FontName=Arial\\,FontSize=")
    assert "PrimaryColour=&H00FFFFFF&" in tok
    assert r"MarginV=160" in tok
    assert r"Alignment=2" in tok


def test_force_style_arg_maps_margin_v_and_alignment_last() -> None:
    """libass force_style list ends with vertical margin and ASS alignment (lower-center presets)."""
    cfg = load_pipeline_config(None)
    minimal = cfg.subtitle_styles["minimal"]
    bold = cfg.subtitle_styles["bold_social"]
    assert _force_style_arg(minimal).split(",")[-2:] == ["MarginV=160", "Alignment=2"]
    assert _force_style_arg(bold).split(",")[-2:] == ["MarginV=152", "Alignment=2"]


def test_force_style_token_bold_social_includes_preset_placement() -> None:
    cfg = load_pipeline_config(None)
    tok = _force_style_token_for_subtitles_filter(cfg.subtitle_styles["bold_social"])
    assert r"MarginV=152" in tok
    assert r"Alignment=2" in tok


def test_build_burnin_video_filter_preserves_encode_profile_geometry_prefix(
    tmp_path: Path,
) -> None:
    """Burn-in must not alter the encode profile filter chain before subtitles=."""
    cfg = load_pipeline_config(None)
    prof = cfg.encode_profiles["shorts-vertical"]
    srt = tmp_path / "cap.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nhello\n", encoding="utf-8")
    vf = build_burnin_video_filter(
        prof,
        subtitle_style=cfg.subtitle_styles["minimal"],
        captions_srt=srt,
    )
    head, sep, tail = vf.partition(",subtitles=cap.srt:force_style=")
    assert sep
    assert head == prof.video_filter
    assert r"MarginV=24" in tail and r"Alignment=2" in tail
    assert f":original_size={prof.width}x{prof.height}" in vf


def test_build_video_filter_differs_between_subtitle_styles(tmp_path: Path) -> None:
    prof = _sample_profile()
    srt = tmp_path / "c.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nhello\n", encoding="utf-8")
    cfg = load_pipeline_config(None)
    m = build_video_filter(
        prof,
        subtitle_style=cfg.subtitle_styles["minimal"],
        captions_srt=srt,
    )
    b = build_video_filter(
        prof,
        subtitle_style=cfg.subtitle_styles["bold_social"],
        captions_srt=srt,
    )
    assert m != b
    assert "subtitles=" in m and "subtitles=" in b
    assert "FontSize=8" in m and "FontName=Arial" in m
    assert "FontSize=10" in b and "Arial Black" in b
    assert "PrimaryColour=&H00FFFFFF&" in m
    assert "PrimaryColour=&H0000FFFF&" in b
    assert "subtitles=c.srt:" in m and "subtitles=c.srt:" in b
    assert r"force_style=FontName=Arial\,FontSize=" in m
    assert r"force_style=FontName=Arial Black\,FontSize=" in b
    assert r"MarginV=36" in m and r"Alignment=2" in m
    assert r"MarginV=34" in b and r"Alignment=2" in b
    assert ":original_size=720x1280" in m and ":original_size=720x1280" in b


def test_build_video_filter_subtitle_font_size_override(tmp_path: Path) -> None:
    prof = _sample_profile()
    srt = tmp_path / "c.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nhello\n", encoding="utf-8")
    cfg = load_pipeline_config(None)
    style = cfg.subtitle_styles["minimal"]
    default_vf = build_video_filter(prof, subtitle_style=style, captions_srt=srt)
    override_vf = build_video_filter(
        prof,
        subtitle_style=style,
        captions_srt=srt,
        subtitle_font_size=99,
    )
    assert "FontSize=8" in default_vf
    assert "FontSize=22" in override_vf
    assert "FontSize=8" not in override_vf


def test_build_ffmpeg_command_matches_profile_fields() -> None:
    prof = _sample_profile()
    inp = Path("/tmp/in.mp4")
    out = Path("/tmp/out.mp4")
    cmd = build_ffmpeg_command(
        "/bin/ffmpeg", input_path=inp, output_path=out, encode_profile=prof
    )
    assert cmd[0] == "/bin/ffmpeg"
    assert "-i" in cmd
    assert cmd[cmd.index("-i") + 1] == str(inp)
    assert "-vf" in cmd
    assert cmd[cmd.index("-vf") + 1] == prof.video_filter
    assert "-r" in cmd and cmd[cmd.index("-r") + 1] == "30"
    assert "-c:v" in cmd and cmd[cmd.index("-c:v") + 1] == "libx264"
    assert "-crf" in cmd and cmd[cmd.index("-crf") + 1] == "28"
    assert "-preset" in cmd and cmd[cmd.index("-preset") + 1] == "veryfast"
    assert "-pix_fmt" in cmd and cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert "-c:a" in cmd and cmd[cmd.index("-c:a") + 1] == "aac"
    assert "-b:a" in cmd and cmd[cmd.index("-b:a") + 1] == "96k"
    assert cmd[-1] == str(out)


def test_build_ffmpeg_command_with_burnin_includes_subtitles_in_vf(
    tmp_path: Path,
) -> None:
    prof = _sample_profile()
    srt = tmp_path / "x.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n", encoding="utf-8")
    cfg = load_pipeline_config(None)
    style = cfg.subtitle_styles["minimal"]
    cmd = build_ffmpeg_command(
        "/bin/ffmpeg",
        input_path=Path("/tmp/in.mp4"),
        output_path=Path("/tmp/out.mp4"),
        encode_profile=prof,
        subtitle_style=style,
        captions_srt=srt,
    )
    vf = cmd[cmd.index("-vf") + 1]
    assert vf.startswith(prof.video_filter + ",subtitles=x.srt:")
    assert "force_style=" in vf
    assert "FontSize=8" in vf
    assert ":original_size=720x1280" in vf
    cmd_o = build_ffmpeg_command(
        "/bin/ffmpeg",
        input_path=Path("/tmp/in.mp4"),
        output_path=Path("/tmp/out.mp4"),
        encode_profile=prof,
        subtitle_style=style,
        captions_srt=srt,
        subtitle_font_size=77,
    )
    vf_o = cmd_o[cmd_o.index("-vf") + 1]
    assert "FontSize=17" in vf_o
    assert "FontSize=8" not in vf_o


def test_write_render_invokes_subprocess_with_profile_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prof = _sample_profile()
    inp = tmp_path / "in.mp4"
    inp.write_bytes(b"not-really-mp4")
    out_dir = tmp_path / "outputs" / "in"
    expected_out = out_dir / f"rendered-{prof.id}.mp4"

    monkeypatch.delenv("SOCIAL_CLIPR_RENDER", raising=False)
    monkeypatch.setattr("social_clipr.render._ffmpeg_path", lambda: "/fake/ffmpeg")

    captured: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(cmd)
        expected_out.parent.mkdir(parents=True, exist_ok=True)
        expected_out.write_bytes(b"fake-mp4")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("social_clipr.render.subprocess.run", fake_run)

    result = write_render_artifact(inp, prof, output_root=tmp_path / "outputs")
    assert result == expected_out
    assert len(captured) == 1
    assert captured[0] == build_ffmpeg_command(
        "/fake/ffmpeg",
        input_path=inp,
        output_path=expected_out,
        encode_profile=prof,
        subtitle_style=None,
        captions_srt=None,
    )


def test_render_raises_when_ffmpeg_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prof = _sample_profile()
    inp = tmp_path / "in.mp4"
    inp.write_bytes(b"x")
    monkeypatch.delenv("SOCIAL_CLIPR_RENDER", raising=False)
    monkeypatch.delenv("SOCIAL_CLIPR_FFMPEG", raising=False)
    monkeypatch.setattr("social_clipr.render._ffmpeg_path", lambda: None)
    with pytest.raises(RenderError, match="ffmpeg was not found"):
        write_render_artifact(inp, prof, output_root=tmp_path / "o")


def test_ffmpeg_path_respects_social_clipr_ffmpeg_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "my-ffmpeg"
    fake.write_text("#!/bin/sh\necho fake\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.delenv("SOCIAL_CLIPR_FFMPEG", raising=False)
    monkeypatch.setenv("SOCIAL_CLIPR_FFMPEG", str(fake))
    assert _ffmpeg_path() == str(fake.resolve())


def test_ffmpeg_path_social_clipr_ffmpeg_name_falls_back_to_which(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil as sh

    monkeypatch.setenv("SOCIAL_CLIPR_FFMPEG", "ffmpeg")
    got = _ffmpeg_path()
    assert got == sh.which("ffmpeg")


def test_render_error_when_social_clipr_ffmpeg_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOCIAL_CLIPR_RENDER", raising=False)
    monkeypatch.setenv("SOCIAL_CLIPR_FFMPEG", str(tmp_path / "nonexistent-ffmpeg-bin"))
    prof = _sample_profile()
    inp = tmp_path / "in.mp4"
    inp.write_bytes(b"x")
    with pytest.raises(RenderError, match="SOCIAL_CLIPR_FFMPEG is set but"):
        write_render_artifact(inp, prof, output_root=tmp_path / "o")


@pytest.mark.skipif(
    not shutil.which("ffmpeg")
    or not shutil.which("ffprobe")
    or not _ffmpeg_has_subtitles_filter(shutil.which("ffmpeg") or ""),
    reason="needs ffmpeg+ffprobe with libass subtitles filter",
)
def test_render_integration_output_matches_profile_dimensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tolerance: video stream matches profile width×height and H.264 (+ AAC)."""
    monkeypatch.delenv("SOCIAL_CLIPR_RENDER", raising=False)
    src = tmp_path / "src.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=0.4:size=640x360:rate=30",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(src),
        ],
        check=True,
        capture_output=True,
    )
    cfg = load_pipeline_config(None)
    prof = cfg.encode_profiles["shorts-vertical"]
    srt = tmp_path / "sub.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nintegration\n",
        encoding="utf-8",
    )
    out = write_render_artifact(
        src,
        prof,
        subtitle_style=cfg.subtitle_styles["minimal"],
        captions_srt=srt,
        output_root=tmp_path / "out",
    )
    assert out.is_file() and out.stat().st_size > 1000
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height",
            "-of",
            "json",
            str(out),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(probe.stdout)
    stream = data["streams"][0]
    assert stream["codec_name"] == "h264"
    assert int(stream["width"]) == prof.width
    assert int(stream["height"]) == prof.height


@pytest.mark.skipif(
    not shutil.which("ffmpeg")
    or not _ffmpeg_has_subtitles_filter(shutil.which("ffmpeg") or ""),
    reason="needs ffmpeg with libass subtitles filter",
)
def test_burnin_outputs_differ_between_style_presets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Burn-in uses config styles; different force_style → different encoded bytes."""
    monkeypatch.delenv("SOCIAL_CLIPR_RENDER", raising=False)

    def _make_mp4(path: Path) -> None:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc=duration=0.5:size=640x360:rate=30",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=48000:cl=stereo",
                "-shortest",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(path),
            ],
            check=True,
            capture_output=True,
        )

    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    _make_mp4(a)
    _make_mp4(b)
    srt = tmp_path / "cap.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:03,000\nstyled line\n",
        encoding="utf-8",
    )
    cfg = load_pipeline_config(None)
    prof = cfg.encode_profiles["shorts-vertical"]
    out_m = write_render_artifact(
        a,
        prof,
        subtitle_style=cfg.subtitle_styles["minimal"],
        captions_srt=srt,
        output_root=tmp_path / "om",
    )
    out_b = write_render_artifact(
        b,
        prof,
        subtitle_style=cfg.subtitle_styles["bold_social"],
        captions_srt=srt,
        output_root=tmp_path / "ob",
    )
    assert out_m.stat().st_size > 1000
    assert out_b.stat().st_size > 1000
    assert out_m.read_bytes() != out_b.read_bytes()
