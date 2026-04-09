"""Exercises remaining lines for 100% package line coverage."""

from __future__ import annotations

import errno
import importlib.util
import json
import os
import runpy
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from social_clipr import bundle
from social_clipr.cli import main
from social_clipr.config_loader import (
    ConfigError,
    load_pipeline_config,
    require_encode_profile,
    require_subtitle_style,
    resolve_config_dir,
)
from social_clipr.ingest import IngestValidationError, validate_input_mp4
from social_clipr.job_preset import JobPresetError, load_job_preset, save_job_preset
from social_clipr.package import write_metadata_draft, write_run_summary
from social_clipr.render import (
    RenderError,
    _ffmpeg_has_subtitles_filter,
    _ffmpeg_path,
    _normalize_ass_colour,
    _scale_subtitle_style_for_ffmpeg_srt,
    _subtitles_srt_token,
    build_burnin_video_filter,
    build_video_filter,
    write_render_artifact,
)
from social_clipr.transcribe import (
    _effective_whisper_params,
    _resolve_whisper_cli_prefix,
    _segment_dicts_from_whisper_json,
    write_transcript_artifacts,
)
from social_clipr.transcript_resume import TranscriptResumeError, resolve_transcript_json_for_resume
from social_clipr.word_cues import WordCue, normalize_word_cues, serialize_word_cues
from tests.test_config_loader import _write_valid_tree


def test___main___exits_with_cli_return_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("social_clipr.cli.main", lambda: 42)
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("social_clipr.__main__", run_name="__main__")
    assert exc.value.code == 42


def test_missing_bundle_files_lists_missing(tmp_path: Path) -> None:
    job = tmp_path / "job"
    job.mkdir()
    missing = bundle.missing_bundle_files(job, "shorts-vertical")
    assert missing  # all artifacts missing
    assert bundle.TRANSCRIPT_JSON_NAME in missing


def test_cli_preset_save_job_preset_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise JobPresetError("nope")

    monkeypatch.setattr("social_clipr.cli.save_job_preset", boom)
    r = main(
        [
            "preset",
            "save",
            "-o",
            str(tmp_path / "p.json"),
            "--profile",
            "p1",
            "--subtitle-style",
            "s1",
        ]
    )
    assert r == 2
    assert "Preset error: nope" in capsys.readouterr().out


def test_cli_run_preset_load_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    inp = tmp_path / "v.mp4"
    inp.write_bytes(b"x")
    r = main(["run", "--input", str(inp), "--preset", str(bad)])
    assert r == 2
    assert "Preset error" in capsys.readouterr().out


def test_resolve_config_dir_explicit_not_dir(tmp_path: Path) -> None:
    f = tmp_path / "f"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(ConfigError, match="not a directory"):
        resolve_config_dir(f)


def test_resolve_config_dir_no_configs_anywhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_root() -> Path:
        return tmp_path / "noroot"

    monkeypatch.setattr("social_clipr.config_loader._package_root", fake_root)
    (tmp_path / "noroot").mkdir()
    with pytest.raises(ConfigError, match="No configs/ directory"):
        resolve_config_dir(None)


def test_load_json_read_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "c"
    _write_valid_tree(root)

    def boom(_self: object, *_a: object, **_k: object) -> str:
        raise OSError("simulated")

    monkeypatch.setattr(Path, "read_text", boom)
    with pytest.raises(ConfigError, match="Cannot read config file"):
        load_pipeline_config(root)


def test_load_json_root_not_object(tmp_path: Path) -> None:
    root = tmp_path / "c"
    _write_valid_tree(root)
    (root / "encode" / "badroot.json").write_text("[1,2]", encoding="utf-8")
    with pytest.raises(ConfigError, match="root must be a JSON object"):
        load_pipeline_config(root)


def test_encode_profile_invalid_dimensions_and_rates(tmp_path: Path) -> None:
    root = tmp_path / "c"
    _write_valid_tree(root)
    base = {
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
    for key, val, msg in [
        ("width", 8, "at least 16"),
        ("frame_rate", 0, "frame_rate"),
        ("audio_bitrate_kbps", 4, "audio_bitrate"),
    ]:
        data = {**base, key: val}
        (root / "encode" / "shorts-vertical.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        with pytest.raises(ConfigError, match=msg):
            load_pipeline_config(root)


def test_encode_video_filter_multiline_rejected(tmp_path: Path) -> None:
    root = tmp_path / "c"
    _write_valid_tree(root)
    data = json.loads(
        (root / "encode" / "shorts-vertical.json").read_text(encoding="utf-8")
    )
    data["video_filter"] = "crop=1080:1920;\nscale=1080:1920"
    (root / "encode" / "shorts-vertical.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="single-line"):
        load_pipeline_config(root)


def test_subtitle_style_validation_errors(tmp_path: Path) -> None:
    root = tmp_path / "c"
    _write_valid_tree(root)
    path = root / "subtitle_styles" / "minimal.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for patch_d, msg in [
        ({"font_size": 4}, "font_size"),
        ({"outline_width": -1}, "outline_width"),
        ({"margin_v": -1}, "margin_v"),
        ({"alignment": 0}, "alignment"),
    ]:
        path.write_text(
            json.dumps({**data, **patch_d}), encoding="utf-8"
        )
        with pytest.raises(ConfigError, match=msg):
            load_pipeline_config(root)


def test_stt_model_and_language_type_errors(tmp_path: Path) -> None:
    root = tmp_path / "c"
    _write_valid_tree(root, stt_engine="stub")
    stt = json.loads((root / "stt.json").read_text(encoding="utf-8"))
    stt["model"] = 123
    (root / "stt.json").write_text(json.dumps(stt), encoding="utf-8")
    with pytest.raises(ConfigError, match="model"):
        load_pipeline_config(root)

    stt = json.loads((root / "stt.json").read_text(encoding="utf-8"))
    stt["model"] = "x"
    stt["language"] = []
    (root / "stt.json").write_text(json.dumps(stt), encoding="utf-8")
    with pytest.raises(ConfigError, match="language"):
        load_pipeline_config(root)


def test_stt_model_key_omitted_defaults_empty(tmp_path: Path) -> None:
    root = tmp_path / "c"
    _write_valid_tree(root)
    stt = json.loads((root / "stt.json").read_text(encoding="utf-8"))
    del stt["model"]
    (root / "stt.json").write_text(json.dumps(stt), encoding="utf-8")
    cfg = load_pipeline_config(root)
    assert cfg.stt.model == ""


def test_stt_model_must_be_string(tmp_path: Path) -> None:
    root = tmp_path / "c"
    _write_valid_tree(root)
    stt = json.loads((root / "stt.json").read_text(encoding="utf-8"))
    stt["model"] = []
    (root / "stt.json").write_text(json.dumps(stt), encoding="utf-8")
    with pytest.raises(ConfigError, match="model"):
        load_pipeline_config(root)


def test_stt_language_json_null(tmp_path: Path) -> None:
    root = tmp_path / "c"
    _write_valid_tree(root)
    stt = json.loads((root / "stt.json").read_text(encoding="utf-8"))
    stt["language"] = None
    (root / "stt.json").write_text(json.dumps(stt), encoding="utf-8")
    cfg = load_pipeline_config(root)
    assert cfg.stt.language == ""


def test_subtitle_style_id_must_match_stem(tmp_path: Path) -> None:
    root = tmp_path / "c"
    _write_valid_tree(root)
    data = json.loads((root / "subtitle_styles/minimal.json").read_text(encoding="utf-8"))
    (root / "subtitle_styles/wrongstem.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="must match file name stem"):
        load_pipeline_config(root)


def test_missing_encode_and_styles_dirs(tmp_path: Path) -> None:
    root = tmp_path / "c"
    root.mkdir()
    (root / "stt.json").write_text('{"engine":"stub","model":"","language":""}')
    with pytest.raises(ConfigError, match="encode"):
        load_pipeline_config(root)
    enc = root / "encode"
    enc.mkdir()
    with pytest.raises(ConfigError, match="subtitle_styles"):
        load_pipeline_config(root)


def test_no_encode_profiles_json(tmp_path: Path) -> None:
    root = tmp_path / "c"
    enc = root / "encode"
    sty = root / "subtitle_styles"
    enc.mkdir(parents=True)
    sty.mkdir(parents=True)
    for name in ("a.json", "b.json"):
        (sty / name).write_text(
            json.dumps(
                {
                    "id": name.replace(".json", ""),
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
    (root / "stt.json").write_text('{"engine":"stub","model":"","language":""}')
    with pytest.raises(ConfigError, match="No encode profiles"):
        load_pipeline_config(root)


def test_require_profile_and_style_keyerror(tmp_path: Path) -> None:
    root = tmp_path / "c"
    _write_valid_tree(root)
    cfg = load_pipeline_config(root)
    with pytest.raises(ConfigError, match="Unknown encode profile"):
        require_encode_profile(cfg, "nope")
    with pytest.raises(ConfigError, match="Unknown subtitle style"):
        require_subtitle_style(cfg, "nope")


def test_expect_str_and_int_via_encode_file(tmp_path: Path) -> None:
    root = tmp_path / "c"
    _write_valid_tree(root)
    data = json.loads(
        (root / "encode" / "shorts-vertical.json").read_text(encoding="utf-8")
    )
    data["id"] = ""
    (root / "encode" / "shorts-vertical.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="invalid string"):
        load_pipeline_config(root)

    data = json.loads(
        (root / "encode" / "shorts-vertical.json").read_text(encoding="utf-8")
    )
    data["id"] = "shorts-vertical"
    data["width"] = True
    (root / "encode" / "shorts-vertical.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="integer"):
        load_pipeline_config(root)


def test_ingest_path_is_directory(tmp_path: Path) -> None:
    d = tmp_path / "x.mp4"
    d.mkdir()
    with pytest.raises(IngestValidationError, match="not a file"):
        validate_input_mp4(str(d))


def test_ingest_open_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "x.mp4"
    p.write_bytes(b"ok")

    def boom(*_a: object, **_k: object) -> object:
        raise OSError("eperm")

    monkeypatch.setattr("pathlib.Path.open", boom)
    with pytest.raises(IngestValidationError, match="not readable"):
        validate_input_mp4(str(p))


def test_job_preset_errors(tmp_path: Path) -> None:
    with pytest.raises(JobPresetError, match="Cannot read"):
        load_job_preset(tmp_path / "missing.json")

    p = tmp_path / "bad.json"
    p.write_text("{", encoding="utf-8")
    with pytest.raises(JobPresetError, match="Invalid JSON"):
        load_job_preset(p)

    p.write_text("[]", encoding="utf-8")
    with pytest.raises(JobPresetError, match="object"):
        load_job_preset(p)

    p.write_text(
        json.dumps(
            {
                "version": 99,
                "profile": "a",
                "subtitle_style": "b",
                "config_dir": None,
                "subtitle_font_size": None,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(JobPresetError, match="version"):
        load_job_preset(p)

    p.write_text(
        json.dumps(
            {
                "version": 1,
                "profile": "",
                "subtitle_style": "b",
                "config_dir": None,
                "subtitle_font_size": None,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(JobPresetError, match="profile"):
        load_job_preset(p)

    p.write_text(
        json.dumps(
            {
                "version": 1,
                "profile": "a\nb",
                "subtitle_style": "b",
                "config_dir": None,
                "subtitle_font_size": None,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(JobPresetError, match="control"):
        load_job_preset(p)

    p.write_text(
        json.dumps(
            {
                "version": 1,
                "profile": "bad id!",
                "subtitle_style": "b",
                "config_dir": None,
                "subtitle_font_size": None,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(JobPresetError, match="match"):
        load_job_preset(p)

    p.write_text(
        json.dumps(
            {
                "version": 1,
                "profile": "ok",
                "subtitle_style": "ok",
                "config_dir": None,
                "subtitle_font_size": True,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(JobPresetError, match="integer"):
        load_job_preset(p)

    p.write_text(
        json.dumps(
            {
                "version": 1,
                "profile": "ok",
                "subtitle_style": "ok",
                "config_dir": 3,
                "subtitle_font_size": None,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(JobPresetError, match="config_dir"):
        load_job_preset(p)

    p.write_text(
        json.dumps(
            {
                "version": 1,
                "profile": "ok",
                "subtitle_style": "ok",
                "config_dir": "  ",
                "subtitle_font_size": None,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(JobPresetError, match="non-empty"):
        load_job_preset(p)


def test_save_job_preset_config_dir_not_dir(tmp_path: Path) -> None:
    f = tmp_path / "f"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(JobPresetError, match="not a directory"):
        save_job_preset(
            tmp_path / "out.json",
            profile="p",
            subtitle_style="s",
            config_dir=f,
        )


def test_write_run_summary_rel_outside_job_dir(tmp_path: Path) -> None:
    job = tmp_path / "job"
    job.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    prof = "shorts-vertical"
    vid = job / f"rendered-{prof}.mp4"
    vid.write_bytes(b"x")
    write_run_summary(
        job,
        profile=prof,
        subtitle_style="minimal",
        subtitle_font_size_effective=44,
        source_input=job / "in.mp4",
        transcript_json=outside,
        transcript_txt=outside,
        captions_srt=outside,
        captions_vtt=outside,
        rendered_mp4=outside,
        render_mode="stub_copy",
    )


def test_render_scale_height_non_positive(sample_encode_and_style: tuple) -> None:
    enc, _sty = sample_encode_and_style
    bad = replace(enc, height=0)
    with pytest.raises(RenderError, match="height"):
        _scale_subtitle_style_for_ffmpeg_srt(_sty, bad.height)


def test_ffmpeg_path_command_name_and_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOCIAL_CLIPR_FFMPEG", raising=False)
    monkeypatch.setattr("shutil.which", lambda _: "/bin/ffmpeg")
    assert _ffmpeg_path() == "/bin/ffmpeg"

    exe = tmp_path / "ff"
    exe.write_text("#!/bin/sh\necho\n", encoding="utf-8")
    exe.chmod(0o755)
    monkeypatch.setenv("SOCIAL_CLIPR_FFMPEG", str(exe))
    assert _ffmpeg_path() == str(exe.resolve())

    monkeypatch.setenv("SOCIAL_CLIPR_FFMPEG", "myff")
    monkeypatch.setattr("shutil.which", lambda n: f"/usr/{n}" if n == "myff" else None)
    assert _ffmpeg_path() == "/usr/myff"


def test_ffmpeg_path_altsep_in_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os, "altsep", "\\")
    monkeypatch.setenv("SOCIAL_CLIPR_FFMPEG", r"foo\bar")
    monkeypatch.setattr("shutil.which", lambda _: "/resolved/foo/bar")
    assert _ffmpeg_path() == "/resolved/foo/bar"


def test_normalize_ass_colour_errors() -> None:
    with pytest.raises(RenderError, match="colour"):
        _normalize_ass_colour("bad")
    with pytest.raises(RenderError, match="Invalid hex"):
        _normalize_ass_colour("&HGGGGGG&")
    with pytest.raises(RenderError, match="6 or 8 digits"):
        _normalize_ass_colour("&HABC&")
    with pytest.raises(RenderError, match="6 or 8 digits"):
        _normalize_ass_colour("&H1234567&")


def test_normalize_ass_colour_eight_digit_hex() -> None:
    assert _normalize_ass_colour("&H11223344&") == "&H11223344&"


def test_ffmpeg_has_subtitles_filter_detects_help_banner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    monkeypatch.setattr(
        "social_clipr.render.subprocess.run",
        lambda *_a, **_k: subprocess.CompletedProcess(
            [], 0, "Filter subtitles\n  ...", ""
        ),
    )
    assert _ffmpeg_has_subtitles_filter("/bin/ffmpeg") is True


def test_subtitles_srt_token_invalid() -> None:
    with pytest.raises(RenderError, match="single name"):
        _subtitles_srt_token("../x.srt")


def test_build_burnin_missing_captions_file(
    sample_encode_and_style: tuple,
) -> None:
    enc, sty = sample_encode_and_style
    missing = Path("/nonexistent/captions.srt")
    with pytest.raises(RenderError, match="not found"):
        build_burnin_video_filter(enc, subtitle_style=sty, captions_srt=missing)


def test_build_video_filter_xor_and_font_only_errors(
    sample_encode_and_style: tuple,
) -> None:
    enc, sty = sample_encode_and_style
    p = Path("x.srt")
    with pytest.raises(ValueError, match="both"):
        build_video_filter(enc, subtitle_style=sty, captions_srt=None)
    with pytest.raises(ValueError, match="both"):
        build_video_filter(enc, subtitle_style=None, captions_srt=p)
    with pytest.raises(ValueError, match="requires"):
        build_video_filter(
            enc, subtitle_style=None, captions_srt=None, subtitle_font_size=12
        )


def test_ffmpeg_has_subtitles_filter_enoexec(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise OSError(errno.ENOEXEC, "Exec format error")

    monkeypatch.setattr("social_clipr.render.subprocess.run", boom)
    with pytest.raises(RenderError, match="native binary"):
        _ffmpeg_has_subtitles_filter("/fake/ffmpeg")


def test_ffmpeg_has_subtitles_filter_other_oserror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise OSError(errno.EACCES, "Permission")

    monkeypatch.setattr("social_clipr.render.subprocess.run", boom)
    with pytest.raises(OSError):
        _ffmpeg_has_subtitles_filter("/fake/ffmpeg")


def test_ffmpeg_has_subtitles_unknown_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    monkeypatch.setattr(
        "social_clipr.render.subprocess.run",
        lambda *_a, **_k: subprocess.CompletedProcess([], 0, "", "unknown filter 'subtitles'"),
    )
    assert _ffmpeg_has_subtitles_filter("/bin/ffmpeg") is False


def test_write_render_ffmpeg_without_subtitles_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sample_encode_and_style: tuple
) -> None:
    enc, sty = sample_encode_and_style
    inp = tmp_path / "in.mp4"
    inp.write_bytes(b"x")
    srt = tmp_path / "c.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    monkeypatch.delenv("SOCIAL_CLIPR_RENDER", raising=False)
    monkeypatch.setattr("social_clipr.render._ffmpeg_path", lambda: "/bin/ffmpeg")
    monkeypatch.setattr("social_clipr.render._ffmpeg_has_subtitles_filter", lambda _: False)
    with pytest.raises(RenderError, match="no `subtitles` filter"):
        write_render_artifact(
            inp, enc, subtitle_style=sty, captions_srt=srt, output_root=tmp_path / "o"
        )


def test_write_render_ffmpeg_missing_with_override_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sample_encode_and_style: tuple
) -> None:
    enc, _ = sample_encode_and_style
    inp = tmp_path / "in.mp4"
    inp.write_bytes(b"x")
    monkeypatch.delenv("SOCIAL_CLIPR_RENDER", raising=False)
    monkeypatch.setattr("social_clipr.render._ffmpeg_path", lambda: None)
    monkeypatch.setenv("SOCIAL_CLIPR_FFMPEG", str(tmp_path / "missing-ffmpeg"))
    with pytest.raises(RenderError, match="SOCIAL_CLIPR_FFMPEG"):
        write_render_artifact(inp, enc, output_root=tmp_path / "o")


def test_write_render_ffmpeg_failed_sigkill_and_negative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sample_encode_and_style: tuple
) -> None:
    enc, sty = sample_encode_and_style
    inp = tmp_path / "in.mp4"
    inp.write_bytes(b"x")
    srt = tmp_path / "c.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    monkeypatch.delenv("SOCIAL_CLIPR_RENDER", raising=False)
    monkeypatch.setattr("social_clipr.render._ffmpeg_path", lambda: "/bin/ffmpeg")
    monkeypatch.setattr("social_clipr.render._ffmpeg_has_subtitles_filter", lambda _: True)

    class CP:
        returncode = -9
        stderr = ""
        stdout = ""

    monkeypatch.setattr("social_clipr.render.subprocess.run", lambda *_a, **_k: CP())
    with pytest.raises(RenderError, match="SIGKILL"):
        write_render_artifact(
            inp,
            enc,
            subtitle_style=sty,
            captions_srt=srt,
            output_root=tmp_path / "o",
        )

    class CP2:
        returncode = -6
        stderr = ""
        stdout = ""

    monkeypatch.setattr("social_clipr.render.subprocess.run", lambda *_a, **_k: CP2())
    with pytest.raises(RenderError, match="signal 6"):
        write_render_artifact(
            inp,
            enc,
            subtitle_style=sty,
            captions_srt=srt,
            output_root=tmp_path / "o",
        )

    class CP3:
        returncode = 1
        stderr = ""
        stdout = ""

    monkeypatch.setattr("social_clipr.render.subprocess.run", lambda *_a, **_k: CP3())
    with pytest.raises(RenderError, match="ffmpeg failed"):
        write_render_artifact(
            inp,
            enc,
            subtitle_style=sty,
            captions_srt=srt,
            output_root=tmp_path / "o",
        )


def test_write_render_copies_srt_when_different_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sample_encode_and_style: tuple
) -> None:
    enc, sty = sample_encode_and_style
    inp = tmp_path / "in.mp4"
    inp.write_bytes(b"x")
    srt = tmp_path / "elsewhere.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    monkeypatch.delenv("SOCIAL_CLIPR_RENDER", raising=False)
    monkeypatch.setattr("social_clipr.render._ffmpeg_path", lambda: "/bin/ffmpeg")
    monkeypatch.setattr("social_clipr.render._ffmpeg_has_subtitles_filter", lambda _: True)

    monkeypatch.setattr(
        "social_clipr.render.subprocess.run",
        lambda *_a, **_k: subprocess.CompletedProcess([], 0, "", ""),
    )
    write_render_artifact(
        inp,
        enc,
        subtitle_style=sty,
        captions_srt=srt,
        output_root=tmp_path / "o",
    )
    job = tmp_path / "o" / "in"
    assert (job / "elsewhere.srt").is_file()


@pytest.fixture
def sample_encode_and_style() -> tuple:
    cfg = load_pipeline_config(None)
    return (cfg.encode_profiles["shorts-vertical"], cfg.subtitle_styles["minimal"])


def test_segment_dicts_from_whisper_json_edges() -> None:
    assert _segment_dicts_from_whisper_json({"segments": "nope"}) == []
    assert _segment_dicts_from_whisper_json({"segments": [{"bad": True}]}) == []
    assert _segment_dicts_from_whisper_json({"segments": [1, {"x": 1}]}) == []
    rows = _segment_dicts_from_whisper_json(
        {
            "segments": [
                {
                    "start": 0,
                    "end": 1,
                    "text": "hi",
                    "words": [
                        {"word": "hi", "start": 0, "end": 1},
                        "bad",
                        {"text": "", "start": 0, "end": 1},
                        {"text": "x", "start": "a", "end": 1},
                    ],
                }
            ]
        }
    )
    assert len(rows) == 1
    assert rows[0]["text"] == "hi"


def test_effective_whisper_params_env_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from social_clipr.config_loader import SpeechToTextConfig

    stt = SpeechToTextConfig(engine="whisper_cli", model="tiny", language="fr")
    monkeypatch.delenv("SOCIAL_CLIPR_WHISPER_MODEL", raising=False)
    monkeypatch.delenv("SOCIAL_CLIPR_WHISPER_LANGUAGE", raising=False)
    m, lang = _effective_whisper_params(stt)
    assert m == "tiny" and lang == "fr"

    monkeypatch.setenv("SOCIAL_CLIPR_WHISPER_LANGUAGE", "")
    m, lang = _effective_whisper_params(stt)
    assert lang is None

    monkeypatch.setenv("SOCIAL_CLIPR_WHISPER_LANGUAGE", "de")
    m, lang = _effective_whisper_params(stt)
    assert lang == "de"


def test_write_transcript_env_stub_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "c"
    _write_valid_tree(root)
    cfg = load_pipeline_config(root)
    inp = tmp_path / "a.mp4"
    inp.write_bytes(b"x")
    monkeypatch.setenv("SOCIAL_CLIPR_TRANSCRIBE", "stub")
    logs: list[str] = []

    write_transcript_artifacts(inp, cfg, output_root=tmp_path / "o", log=logs.append)
    assert any("SOCIAL_CLIPR_TRANSCRIBE" in m for m in logs)


def test_write_transcript_config_stub_engine_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "c"
    _write_valid_tree(root, stt_engine="stub")
    cfg = load_pipeline_config(root)
    inp = tmp_path / "a.mp4"
    inp.write_bytes(b"x")
    monkeypatch.delenv("SOCIAL_CLIPR_TRANSCRIBE", raising=False)
    logs: list[str] = []
    write_transcript_artifacts(inp, cfg, output_root=tmp_path / "o", log=logs.append)
    assert any("engine=stub" in m for m in logs)


def test_try_whisper_cli_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from social_clipr.transcribe import _try_whisper_cli

    root = tmp_path / "c"
    _write_valid_tree(root, stt_engine="whisper_cli", stt_model="tiny")
    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"x")
    job_dir = tmp_path / "out" / "clip"
    job_dir.mkdir(parents=True)

    monkeypatch.setattr("social_clipr.transcribe._resolve_whisper_cli_prefix", lambda: (None, True))
    logs: list[str] = []
    assert _try_whisper_cli(inp, job_dir, model="tiny", language=None, log=logs.append) is None
    assert logs

    monkeypatch.setattr(
        "social_clipr.transcribe._resolve_whisper_cli_prefix",
        lambda: (["/bin/false"], False),
    )
    monkeypatch.setattr(
        "social_clipr.transcribe.subprocess.run",
        lambda *_a, **_k: __import__("subprocess").CompletedProcess([], 1, "", "err"),
    )
    logs.clear()
    assert _try_whisper_cli(inp, job_dir, model="tiny", language="en", log=logs.append) is None
    assert logs

    def fake_run(cmd: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
        out_dir = cmd[cmd.index("--output_dir") + 1]
        Path(out_dir, "clip.json").write_text('{"segments":[]}', encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(
        "social_clipr.transcribe._resolve_whisper_cli_prefix",
        lambda: (["/whisper"], False),
    )
    monkeypatch.setattr("social_clipr.transcribe.subprocess.run", fake_run)
    logs.clear()
    assert _try_whisper_cli(inp, job_dir, model="tiny", language=None, log=logs.append) is None
    assert any("no segments" in m for m in logs)

    def fake_run_ok(cmd: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
        out_dir = cmd[cmd.index("--output_dir") + 1]
        Path(out_dir, "clip.json").write_text(
            json.dumps({"segments": [{"start": 0, "end": 1, "text": "hi"}]}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("social_clipr.transcribe.subprocess.run", fake_run_ok)
    logs.clear()
    out = _try_whisper_cli(inp, job_dir, model="tiny", language=None, log=logs.append)
    assert out is not None
    assert any("using whisper_cli" in m for m in logs)

    def fake_run2(cmd: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("social_clipr.transcribe.subprocess.run", fake_run2)
    logs.clear()
    assert _try_whisper_cli(inp, job_dir, model="tiny", language=None, log=logs.append) is None
    assert any("no JSON" in m for m in logs)


def test_try_faster_whisper_import_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from social_clipr.transcribe import _try_faster_whisper

    inp = tmp_path / "c.mp4"
    inp.write_bytes(b"x")
    job_dir = tmp_path / "j"
    job_dir.mkdir()
    logs: list[str] = []

    import builtins

    real_import = builtins.__import__

    def no_fw(name: str, *a: object, **kw: object) -> object:
        if name == "faster_whisper":
            raise ImportError("no")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", no_fw)
    assert (
        _try_faster_whisper(inp, job_dir, model="tiny", language=None, log=logs.append)
        is None
    )
    assert logs


def test_try_faster_whisper_runtime_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from social_clipr.transcribe import _try_faster_whisper

    inp = tmp_path / "c.mp4"
    inp.write_bytes(b"x")
    job_dir = tmp_path / "j"
    job_dir.mkdir()
    logs: list[str] = []

    class BoomModel:
        def __init__(self, *_a: object, **_k: object) -> None:
            raise RuntimeError("boom")

    fake_mod = MagicMock()
    fake_mod.WhisperModel = BoomModel
    monkeypatch.setitem(__import__("sys").modules, "faster_whisper", fake_mod)
    monkeypatch.delenv("SOCIAL_CLIPR_TRANSCRIBE", raising=False)
    assert (
        _try_faster_whisper(inp, job_dir, model="tiny", language=None, log=logs.append)
        is None
    )
    assert any("faster_whisper error" in m for m in logs)


def test_try_faster_whisper_success_writes_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from social_clipr.transcribe import _try_faster_whisper

    class _EmptyWord:
        word = "  "
        start = 0.0
        end = 0.1

    class _BadFloatWord:
        word = "x"
        start = "nope"
        end = 1.0

    class _OkWord:
        word = "ok"
        start = 0.0
        end = 0.05

    class _SegA:
        text = " plain "
        start = 0.0
        end = 0.5
        words = None

    class _SegB:
        text = " with_words "
        start = 0.5
        end = 1.0
        words = [_EmptyWord(), _BadFloatWord(), _OkWord()]

    class _Model:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def transcribe(self, *_a: object, **_k: object) -> tuple[object, dict[str, float]]:
            def _gen() -> object:
                yield _SegA()
                yield _SegB()

            return _gen(), {"duration": 1.0}

    fake_mod = MagicMock()
    fake_mod.WhisperModel = _Model
    monkeypatch.setitem(__import__("sys").modules, "faster_whisper", fake_mod)
    monkeypatch.delenv("SOCIAL_CLIPR_TRANSCRIBE", raising=False)

    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"x")
    job_dir = tmp_path / "out" / "clip"
    job_dir.mkdir(parents=True)
    logs: list[str] = []
    out = _try_faster_whisper(
        inp, job_dir, model="tiny", language=None, log=logs.append
    )
    assert out is not None
    assert any("using faster_whisper" in m for m in logs)
    payload = json.loads(out["json"].read_text(encoding="utf-8"))
    assert payload["engine"].startswith("faster_whisper:")
    assert payload["segment_count"] == 2


def test_write_transcript_faster_whisper_returns_try_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "c"
    _write_valid_tree(root, stt_engine="faster_whisper", stt_model="tiny")
    cfg = load_pipeline_config(root)
    inp = tmp_path / "z.mp4"
    inp.write_bytes(b"x")
    monkeypatch.delenv("SOCIAL_CLIPR_TRANSCRIBE", raising=False)
    job_dir = tmp_path / "o" / "z"
    job_dir.mkdir(parents=True)
    fake_json = job_dir / "transcript.json"
    fake_txt = job_dir / "transcript.txt"
    fake_json.write_text("{}", encoding="utf-8")
    fake_txt.write_text("", encoding="utf-8")
    want = {"json": fake_json, "txt": fake_txt}

    monkeypatch.setattr(
        "social_clipr.transcribe._try_faster_whisper", lambda *_a, **_k: want
    )
    assert write_transcript_artifacts(inp, cfg, output_root=tmp_path / "o") == want


def test_resolve_whisper_cli_prefix_python_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_find = importlib.util.find_spec

    def fake_find(name: str, package: str | None = None) -> object | None:
        if name == "whisper":
            return object()
        return real_find(name, package)

    monkeypatch.setattr(
        "social_clipr.transcribe.importlib.util.find_spec", fake_find
    )
    prefix, skipped = _resolve_whisper_cli_prefix()
    assert prefix == [sys.executable, "-m", "whisper"]
    assert skipped is False


def test_resolve_whisper_cli_prefix_which_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "social_clipr.transcribe.importlib.util.find_spec", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        "social_clipr.transcribe.shutil.which", lambda _: "/opt/whisper"
    )
    monkeypatch.setattr(
        "social_clipr.transcribe._path_looks_like_pyenv_shim", lambda _e: False
    )
    prefix, skipped = _resolve_whisper_cli_prefix()
    assert prefix == ["/opt/whisper"]
    assert skipped is False


def test_resolve_whisper_cli_prefix_no_whisper_on_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "social_clipr.transcribe.importlib.util.find_spec", lambda *_a, **_k: None
    )
    monkeypatch.setattr("social_clipr.transcribe.shutil.which", lambda _: None)
    prefix, skipped = _resolve_whisper_cli_prefix()
    assert prefix is None
    assert skipped is False


def test_try_faster_whisper_empty_segments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from social_clipr.transcribe import _try_faster_whisper

    class _Model:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def transcribe(self, *_a: object, **_k: object) -> tuple[object, dict[str, float]]:
            return iter(()), {}

    fake_mod = MagicMock()
    fake_mod.WhisperModel = _Model
    monkeypatch.setitem(__import__("sys").modules, "faster_whisper", fake_mod)
    monkeypatch.delenv("SOCIAL_CLIPR_TRANSCRIBE", raising=False)

    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"x")
    job_dir = tmp_path / "out" / "clip"
    job_dir.mkdir(parents=True)
    logs: list[str] = []
    assert (
        _try_faster_whisper(inp, job_dir, model="tiny", language=None, log=logs.append)
        is None
    )
    assert any("no segments" in m for m in logs)


def test_write_transcript_whisper_fail_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "c"
    _write_valid_tree(root, stt_engine="whisper_cli", stt_model="tiny")
    cfg = load_pipeline_config(root)
    inp = tmp_path / "z.mp4"
    inp.write_bytes(b"x")
    monkeypatch.delenv("SOCIAL_CLIPR_TRANSCRIBE", raising=False)
    monkeypatch.setattr(
        "social_clipr.transcribe._try_whisper_cli", lambda *_a, **_k: None
    )
    logs: list[str] = []
    write_transcript_artifacts(inp, cfg, output_root=tmp_path / "o", log=logs.append)
    assert any("whisper CLI not found" in m for m in logs)


def test_write_transcript_unknown_engine_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "c"
    _write_valid_tree(root, stt_engine="stub")
    cfg = load_pipeline_config(root)
    cfg2 = replace(cfg, stt=replace(cfg.stt, engine="not_a_real_engine"))
    inp = tmp_path / "z.mp4"
    inp.write_bytes(b"x")
    monkeypatch.delenv("SOCIAL_CLIPR_TRANSCRIBE", raising=False)
    out = write_transcript_artifacts(inp, cfg2, output_root=tmp_path / "o")
    payload = json.loads(out["json"].read_text(encoding="utf-8"))
    assert payload["engine"] == "stub"


def test_resolve_transcript_json_read_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inp = tmp_path / "a.mp4"
    inp.write_bytes(b"x")
    root = tmp_path / "o"
    job = root / "a"
    job.mkdir(parents=True)
    tj = job / "transcript.json"
    tj.write_text("{}", encoding="utf-8")

    def boom(*_a: object, **_k: object) -> str:
        raise OSError("nope")

    monkeypatch.setattr(Path, "read_text", boom)
    with pytest.raises(TranscriptResumeError, match="Cannot read"):
        resolve_transcript_json_for_resume(inp, output_root=root)


def test_word_cues_normalize_branches() -> None:
    assert normalize_word_cues({"word_cues": "x"}) == []
    assert normalize_word_cues({"word_cues": [1]}) == []
    assert normalize_word_cues(
        {"word_cues": [{"text": "  ", "start": 0, "end": 1}]}
    ) == []
    assert normalize_word_cues(
        {"word_cues": [{"text": "a", "start": "not-a-float", "end": 1}]}
    ) == []
    assert normalize_word_cues({"segments": 1}) == []
    assert normalize_word_cues({"segments": ["nope"]}) == []
    assert normalize_word_cues({"segments": [{"text": "", "start": 0, "end": 1}]}) == []
    assert normalize_word_cues({"segments": [{"text": "   ", "start": 0, "end": 1}]}) == []
    assert normalize_word_cues(
        {"segments": [{"text": "a", "start": "bad", "end": 1}]}
    ) == []
    swap = normalize_word_cues({"segments": [{"text": "a", "start": 5, "end": 1}]})
    assert len(swap) == 1 and swap[0].start <= swap[0].end

    p = {"segments": [{"text": "one two", "start": 0, "end": 1.0}]}
    cues = normalize_word_cues(p)
    assert len(cues) == 2
    p2 = {"segments": [{"text": "only", "start": 1.0, "end": 1.0}]}
    assert len(normalize_word_cues(p2)) == 1
    p3 = {"segments": [{"text": "a b", "start": 0, "end": 0.5}]}
    assert len(normalize_word_cues(p3)) == 2
    p4 = {"segments": [{"text": "w1 w2 w3", "start": 0, "end": 0.2}]}
    assert len(normalize_word_cues(p4)) == 3
    p_pack = {"segments": [{"text": "a b c", "start": 0, "end": 0.2}]}
    assert len(normalize_word_cues(p_pack)) == 3
    p_starved = {"segments": [{"text": "a b c", "start": 0, "end": 0.15}]}
    assert len(normalize_word_cues(p_starved)) == 3
    p5 = {
        "segments": [
            {
                "text": "x y",
                "start": 0,
                "end": 0.1,
                "words": [
                    {"text": "bad", "start": "x", "end": 1},
                    {"text": "ok", "start": 0, "end": 0.05},
                ],
            }
        ]
    }
    assert normalize_word_cues(p5)
    p6 = {
        "segments": [
            {
                "text": "split me",
                "start": 0,
                "end": 1.0,
                "words": ["bad", {"text": "", "start": 0, "end": 1}],
            }
        ]
    }
    assert len(normalize_word_cues(p6)) == 2
    assert serialize_word_cues([WordCue(0.0, 1.0, "a")]) == [
        {"start": 0.0, "end": 1.0, "text": "a"}
    ]


def test_write_metadata_transcript_source(tmp_path: Path) -> None:
    job = tmp_path / "j"
    job.mkdir()
    write_metadata_draft(
        job,
        stem="s",
        encode_profile_id="shorts-vertical",
        subtitle_style_id="minimal",
        subtitle_font_size_effective=44,
        source_filename="x.mp4",
        render_mode="stub_copy",
        transcript_source="resume",
    )
    data = json.loads((job / "metadata_draft.json").read_text(encoding="utf-8"))
    assert data["transcript_source"] == "resume"


def test_write_run_summary_transcript_source(tmp_path: Path) -> None:
    job = tmp_path / "j"
    job.mkdir()
    prof = "shorts-vertical"
    vid = job / f"rendered-{prof}.mp4"
    vid.write_bytes(b"x")
    p = tmp_path / "t.json"
    p.write_text("{}", encoding="utf-8")
    write_run_summary(
        job,
        profile=prof,
        subtitle_style="minimal",
        subtitle_font_size_effective=44,
        source_input=job / "in.mp4",
        transcript_json=p,
        transcript_txt=p,
        captions_srt=p,
        captions_vtt=p,
        rendered_mp4=vid,
        render_mode="stub_copy",
        transcript_source="edited",
    )
    data = json.loads((job / "run_summary.json").read_text(encoding="utf-8"))
    assert data["transcript_source"] == "edited"
    assert data["transcribe_skipped"] is True


def test_video_filter_proves_crop_mismatch_scale_only(tmp_path: Path) -> None:
    """_video_filter_proves_output_dimensions: crop present but wrong size → invalid."""
    root = tmp_path / "c"
    _write_valid_tree(root)
    data = json.loads(
        (root / "encode" / "shorts-vertical.json").read_text(encoding="utf-8")
    )
    data["video_filter"] = "scale=1080:1920,crop=100:100"
    (root / "encode" / "shorts-vertical.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="video_filter must contain"):
        load_pipeline_config(root)
